from fastapi import Form

@router.post(
    "/upload", response_model=InsertResponse, dependencies=[Depends(combined_auth)]
)
async def upload_to_input_dir(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: str = Form(None),   # ✅ Added metadata field
):
    """
    Upload a file to the input directory and index it.

    This endpoint accepts a file and optional metadata in Form-Data format,
    validates it, saves it in the input directory, stores metadata next to it,
    and then triggers background processing for indexing.

    Args:
        background_tasks: FastAPI BackgroundTasks for async processing
        file (UploadFile): The file to be uploaded
        metadata (str): Optional JSON metadata (sent as Form-Data)

    Returns:
        InsertResponse: Status, message, and track_id

    Raises:
        HTTPException: If file type is unsupported or internal error occurs
    """
    try:
        # ✅ Sanitize filename
        safe_filename = sanitize_filename(file.filename, doc_manager.input_dir)

        # ✅ Validate file extension
        if not doc_manager.is_supported_file(safe_filename):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type. Supported types: {doc_manager.supported_extensions}",
            )

        # ✅ Check if file already exists in database or filesystem
        existing_doc_data = await rag.doc_status.get_doc_by_file_path(safe_filename)
        if existing_doc_data:
            status = existing_doc_data.get("status", "unknown")
            return InsertResponse(
                status="duplicated",
                message=f"File '{safe_filename}' already exists in document storage (Status: {status}).",
                track_id="",
            )

        file_path = doc_manager.input_dir / safe_filename
        if file_path.exists():
            return InsertResponse(
                status="duplicated",
                message=f"File '{safe_filename}' already exists in the input directory.",
                track_id="",
            )

        # ✅ Save the uploaded file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ✅ Generate tracking ID
        track_id = generate_track_id("upload")

        # ✅ Save metadata if provided
        if metadata:
            import json
            try:
                parsed_metadata = json.loads(metadata)
                if not isinstance(parsed_metadata, dict):
                    parsed_metadata = {"raw_metadata": metadata}
            except Exception:
                parsed_metadata = {"raw_metadata": metadata}

            meta_path = str(file_path) + ".meta.json"
            with open(meta_path, "w", encoding="utf-8") as meta_file:
                json.dump(parsed_metadata, meta_file, ensure_ascii=False, indent=2)

            logger.info(f"✅ Metadata saved for {safe_filename}: {meta_path}")

        # ✅ Start background indexing
        background_tasks.add_task(pipeline_index_file, rag, file_path, track_id)

        return InsertResponse(
            status="success",
            message=f"File '{safe_filename}' uploaded successfully. Processing will continue in background.",
            track_id=track_id,
        )

    except Exception as e:
        logger.error(f"Error /documents/upload: {file.filename}: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
