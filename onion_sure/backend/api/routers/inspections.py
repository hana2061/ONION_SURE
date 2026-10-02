"""
Inspection and Grading Orchestration Router
Smart India Hackathon 2026 - Problem Statement PS26031

Features:
- Inspection lifecycle orchestration
- Multipart image file upload with storage abstraction (no binaries in DB)
- Image metadata registration
- AI observation and deterministic grading persistence
- Manual review / grade overrides
- Inspection finalization and report generation
- Pagination and status filtering
"""

from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...models.entities import (
    User,
    Inspection,
    InspectionImage,
    OnionDetection,
    GradeResult as DBGradeResult,
    Report,
)
from ...schemas.api_schemas import (
    InspectionCreate,
    InspectionResponse,
    ImageMetadataCreate,
    ImageMetadataResponse,
    PersistGradeResultRequest,
    GradeResultResponse,
    ManualReviewCreate,
    ManualReviewResponse,
    ReportResponse,
    PaginatedResponse,
    OnionDetectionResponse,
)
from ...services.inspection_service import InspectionService
from ...services.grading_persistence_service import GradingPersistenceService
from ...services.report_service import ReportService
from ...services.storage_service import image_storage_service
from ...security import get_current_user
from ...config import settings

router = APIRouter(prefix="/inspections", tags=["Inspections"])


@router.post("", response_model=InspectionResponse, status_code=status.HTTP_201_CREATED)
def create_inspection(insp_in: InspectionCreate, db: Session = Depends(get_db)):
    """Creates a new inspection record or returns existing matching code (idempotent)."""
    try:
        return InspectionService.create_inspection(
            db=db,
            lot_id=insp_in.lot_id,
            inspector_id=insp_in.inspector_id,
            inspection_code=insp_in.inspection_code,
            sample_size=insp_in.sample_size,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{inspection_id}", response_model=InspectionResponse)
def get_inspection(inspection_id: str, db: Session = Depends(get_db)):
    """Retrieves full inspection state including aggregated grade percentages."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


@router.patch("/{inspection_id}/status", response_model=InspectionResponse)
def update_inspection_status(
    inspection_id: str,
    status: str,
    db: Session = Depends(get_db),
):
    """Updates inspection status (e.g. DRAFT, CAPTURING, PROCESSING, COMPLETED)."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    inspection.status = status.upper()
    db.commit()
    db.refresh(inspection)
    return inspection


@router.get("", response_model=Union[PaginatedResponse[InspectionResponse], List[InspectionResponse]])
def list_inspections(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    lot_id: Optional[str] = None,
    inspector_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Lists inspections with optional filtering and pagination."""
    query = db.query(Inspection)
    if lot_id:
        query = query.filter(Inspection.lot_id == lot_id)
    if inspector_id:
        query = query.filter(Inspection.inspector_id == inspector_id)
    if status:
        query = query.filter(Inspection.status == status.upper())

    total = query.count()

    if page is not None:
        p_size = page_size or 20
        offset = (page - 1) * p_size
        items = query.order_by(Inspection.created_at.desc()).offset(offset).limit(p_size).all()
        total_pages = (total + p_size - 1) // p_size if total > 0 else 1
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages,
        )

    return query.order_by(Inspection.created_at.desc()).offset(skip).limit(limit).all()


# ==============================================================================
# IMAGE UPLOAD & METADATA ATTACHMENT
# ==============================================================================

@router.post("/{inspection_id}/upload-image", response_model=ImageMetadataResponse, status_code=status.HTTP_201_CREATED)
async def upload_inspection_image(
    inspection_id: str,
    file: UploadFile = File(...),
    calibration_detected: bool = Form(False),
    pixels_per_mm: Optional[float] = Form(None),
    calibration_method: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Accepts multipart image file upload:
    - Validates file content type and size limits
    - Stores file using ImageStorageService abstraction (local / S3)
    - Records metadata, SHA256, and optical quality in PostgreSQL (NO binary stored in DB)
    """
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # Validate content type
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{file.content_type}'. Must be one of {allowed_types}",
        )

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds maximum permitted size of {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # Store via storage provider
    storage_meta = image_storage_service.save_image(
        content=content,
        filename=file.filename or "capture.jpg",
        content_type=file.content_type or "image/jpeg",
    )

    return InspectionService.attach_image_metadata(
        db=db,
        inspection_id=inspection_id,
        storage_key=storage_meta["storage_key"],
        filename=storage_meta["filename"],
        file_size_bytes=storage_meta["file_size_bytes"],
        content_type=storage_meta["content_type"],
        sha256_hash=storage_meta["sha256_hash"],
        quality_status="PASSED",
        calibration_detected=calibration_detected,
        pixels_per_mm=pixels_per_mm,
        calibration_method=calibration_method,
    )


@router.post("/{inspection_id}/images", response_model=ImageMetadataResponse, status_code=status.HTTP_201_CREATED)
def attach_inspection_image_metadata(
    inspection_id: str,
    img_in: ImageMetadataCreate,
    db: Session = Depends(get_db),
):
    """Attaches validated image metadata without storing large binaries in PostgreSQL."""
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    return InspectionService.attach_image_metadata(
        db=db,
        inspection_id=inspection_id,
        storage_key=img_in.storage_key,
        filename=img_in.filename,
        file_size_bytes=img_in.file_size_bytes,
        content_type=img_in.content_type,
        sha256_hash=img_in.sha256_hash,
        quality_status=img_in.quality_status,
        blur_variance=img_in.blur_variance,
        mean_brightness=img_in.mean_brightness,
        contrast_std=img_in.contrast_std,
        quality_reasons=img_in.quality_reasons,
        calibration_detected=img_in.calibration_detected,
        pixels_per_mm=img_in.pixels_per_mm,
        calibration_method=img_in.calibration_method,
    )


@router.get("/{inspection_id}/images", response_model=List[ImageMetadataResponse])
def list_inspection_images(inspection_id: str, db: Session = Depends(get_db)):
    """Lists all images associated with an inspection."""
    return db.query(InspectionImage).filter(InspectionImage.inspection_id == inspection_id).all()


@router.get("/{inspection_id}/detections", response_model=List[OnionDetectionResponse])
def list_inspection_detections(inspection_id: str, db: Session = Depends(get_db)):
    """Lists individual onion detections for all images in an inspection."""
    return (
        db.query(OnionDetection)
        .join(InspectionImage, OnionDetection.image_id == InspectionImage.id)
        .filter(InspectionImage.inspection_id == inspection_id)
        .all()
    )


# ==============================================================================
# GRADING, REVIEWS, AND FINALIZATION
# ==============================================================================

@router.post("/{inspection_id}/grade", response_model=List[GradeResultResponse])
def evaluate_and_persist_grading(
    inspection_id: str,
    grade_req: PersistGradeResultRequest,
    db: Session = Depends(get_db),
):
    """
    Feeds structured observations into the deterministic grading engine,
    persisting detections, measurements, defect predictions, decision traces,
    and updating the inspection lot summary.
    """
    try:
        observations_dicts = [obs.model_dump() for obs in grade_req.observations]
        _, db_grade_results = GradingPersistenceService.evaluate_and_persist_inspection(
            db=db,
            inspection_id=inspection_id,
            observations_data=observations_dicts,
            policy_version_str=grade_req.policy_version,
            model_version_str=grade_req.model_version,
        )
        return db_grade_results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{inspection_id}/grade-results", response_model=List[GradeResultResponse])
def list_inspection_grade_results(inspection_id: str, db: Session = Depends(get_db)):
    """Lists all individual onion grade results and decision traces for an inspection."""
    return db.query(DBGradeResult).filter(DBGradeResult.inspection_id == inspection_id).all()


@router.post("/{inspection_id}/demo-grade", response_model=List[GradeResultResponse])
def run_demo_grade(
    inspection_id: str,
    outcome: str = "GRADE_A",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Runs the deterministic AI demo-mode grading workflow for the given inspection."""
    try:
        return InspectionService.run_demo_grading(
            db=db,
            inspection_id=inspection_id,
            demo_outcome=outcome,
            actor_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{inspection_id}/manual-review", response_model=ManualReviewResponse)
def submit_manual_review(
    inspection_id: str,
    review_in: ManualReviewCreate,
    db: Session = Depends(get_db),
):
    """Submits a human inspector grade override with audit trail."""
    try:
        return InspectionService.apply_manual_review(
            db=db,
            grade_result_id=review_in.grade_result_id,
            reviewer_id=review_in.reviewer_id,
            reviewed_grade=review_in.reviewed_grade,
            reason=review_in.reason,
            comments=review_in.comments,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{inspection_id}/finalize", response_model=ReportResponse)
def finalize_inspection_and_generate_report(
    inspection_id: str,
    actor_id: str = "system",
    db: Session = Depends(get_db),
):
    """Finalizes an inspection and generates the immutable digital quality report with PDF and QR hash."""
    try:
        return ReportService.finalize_and_generate_report(
            db=db,
            inspection_id=inspection_id,
            actor_id=actor_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
