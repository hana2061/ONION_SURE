"""
Inspection Management and Finalization Service
Smart India Hackathon 2026 - Problem Statement PS26031

Handles:
- Idempotent inspection registration
- Image metadata attachment
- Manual review override with audit trail
- Report finalization with verifiable QR hash
"""

import uuid
import hashlib
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ..models import (
    Inspection,
    InspectionImage,
    GradeResult as DBGradeResult,
    ManualReview,
    Report,
    Lot,
)
from .audit_service import AuditService
from .grading_persistence_service import GradingPersistenceService


class InspectionService:
    @staticmethod
    def create_inspection(
        db: Session,
        lot_id: str,
        inspector_id: str,
        inspection_code: Optional[str] = None,
        sample_size: int = 0,
    ) -> Inspection:
        """Creates or idempotently retrieves an inspection."""
        code = inspection_code or f"INSP-{uuid.uuid4().hex[:8].upper()}"

        existing = db.query(Inspection).filter(Inspection.inspection_code == code).first()
        if existing:
            return existing

        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if not lot:
            raise ValueError(f"Lot '{lot_id}' does not exist.")

        inspection = Inspection(
            inspection_code=code,
            lot_id=lot_id,
            inspector_id=inspector_id,
            sample_size=sample_size,
            status="CAPTURING",
        )
        db.add(inspection)
        db.flush()

        AuditService.log_event(
            db=db,
            actor_id=inspector_id,
            action="CREATE_INSPECTION",
            entity_type="Inspection",
            entity_id=inspection.id,
            new_values={"inspection_code": code, "lot_id": lot_id},
        )
        db.commit()
        db.refresh(inspection)
        return inspection

    @staticmethod
    def attach_image_metadata(
        db: Session,
        inspection_id: str,
        storage_key: str,
        filename: str,
        file_size_bytes: int,
        content_type: str = "image/jpeg",
        sha256_hash: Optional[str] = None,
        quality_status: str = "PASSED",
        blur_variance: Optional[float] = None,
        mean_brightness: Optional[float] = None,
        contrast_std: Optional[float] = None,
        quality_reasons: Optional[list] = None,
        calibration_detected: bool = False,
        pixels_per_mm: Optional[float] = None,
        calibration_method: Optional[str] = None,
    ) -> InspectionImage:
        """Attaches validated image metadata without storing binary in database."""
        image = InspectionImage(
            inspection_id=inspection_id,
            storage_key=storage_key,
            filename=filename,
            file_size_bytes=file_size_bytes,
            content_type=content_type,
            sha256_hash=sha256_hash,
            quality_status=quality_status,
            blur_variance=blur_variance,
            mean_brightness=mean_brightness,
            contrast_std=contrast_std,
            quality_reasons=quality_reasons or [],
            calibration_detected=calibration_detected,
            pixels_per_mm=pixels_per_mm,
            calibration_method=calibration_method,
        )
        db.add(image)
        db.commit()
        db.refresh(image)
        return image

    @staticmethod
    def apply_manual_review(
        db: Session,
        grade_result_id: str,
        reviewer_id: str,
        reviewed_grade: str,
        reason: str,
        comments: Optional[str] = None,
    ) -> ManualReview:
        """
        Applies a human review override:
        Preserves original AI grade and logs an immutable manual review record.
        """
        grade_result = db.query(DBGradeResult).filter(DBGradeResult.id == grade_result_id).first()
        if not grade_result:
            raise ValueError(f"GradeResult '{grade_result_id}' not found.")

        original_grade = grade_result.grade
        grade_result.grade = reviewed_grade
        grade_result.requires_review = False

        review = ManualReview(
            inspection_id=grade_result.inspection_id,
            grade_result_id=grade_result.id,
            reviewer_id=reviewer_id,
            original_grade=original_grade,
            reviewed_grade=reviewed_grade,
            reason=reason,
            comments=comments,
            status="APPROVED",
        )
        db.add(review)

        # Update decision trace
        trace = list(grade_result.decision_trace)
        trace.append({
            "step": len(trace) + 1,
            "check": "manual_review_override",
            "reviewer_id": reviewer_id,
            "original_grade": original_grade,
            "reviewed_grade": reviewed_grade,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        grade_result.decision_trace = trace

        AuditService.log_event(
            db=db,
            actor_id=reviewer_id,
            action="MANUAL_GRADE_OVERRIDE",
            entity_type="GradeResult",
            entity_id=grade_result.id,
            old_values={"grade": original_grade},
            new_values={"grade": reviewed_grade, "reason": reason},
        )
        db.commit()
        db.refresh(review)
        return review

    @staticmethod
    def run_demo_grading(
        db: Session,
        inspection_id: str,
        demo_outcome: str = "GRADE_A",
        actor_id: Optional[str] = None,
    ) -> List[DBGradeResult]:
        """Runs a deterministic demo grading flow and stores a real grading result."""
        inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
        if not inspection:
            raise ValueError(f"Inspection '{inspection_id}' not found.")

        image = db.query(InspectionImage).filter(InspectionImage.inspection_id == inspection_id).first()
        if not image:
            image = InspectionImage(
                inspection_id=inspection_id,
                storage_key=f"demo://{inspection.inspection_code}/sample.jpg",
                filename=f"{inspection.inspection_code}.jpg",
                file_size_bytes=120000,
                content_type="image/jpeg",
                sha256_hash=hashlib.sha256(f"demo:{inspection.id}".encode("utf-8")).hexdigest(),
                quality_status="PASSED",
                calibration_detected=True,
                pixels_per_mm=3.2,
                calibration_method="demo_mode",
            )
            db.add(image)
            db.flush()

        outcomes = {
            "GRADE_A": {
                "defect_class": "HEALTHY",
                "defect_confidence": 0.97,
                "diameter_mm": 52.0,
                "reason": "Healthy sample with acceptable size and no critical defects.",
            },
            "URS": {
                "defect_class": "DAMAGED",
                "defect_confidence": 0.74,
                "diameter_mm": 48.0,
                "reason": "Minor surface damage but within URS tolerance. Requires conditional acceptance.",
            },
            "REJECT": {
                "defect_class": "ROTTEN",
                "defect_confidence": 0.95,
                "diameter_mm": 41.0,
                "reason": "Critical rot and undersized onion exceed rejection thresholds.",
            },
            "MANUAL_REVIEW": {
                "defect_class": "UNKNOWN",
                "defect_confidence": 0.49,
                "diameter_mm": 50.0,
                "reason": "Evidence quality is borderline and requires manual review.",
            },
        }
        selected = outcomes.get(demo_outcome.upper(), outcomes["GRADE_A"])

        observations = [{
            "image_id": image.id,
            "onion_index": "onion_001",
            "bbox_x": 10.0,
            "bbox_y": 20.0,
            "bbox_w": 180.0,
            "bbox_h": 180.0,
            "detection_confidence": 0.94,
            "defect_class": selected["defect_class"],
            "defect_confidence": selected["defect_confidence"],
            "all_probabilities": {
                "HEALTHY": 0.10 if selected["defect_class"] != "HEALTHY" else 0.94,
                "DAMAGED": 0.15 if selected["defect_class"] != "DAMAGED" else 0.91,
                "ROTTEN": 0.10 if selected["defect_class"] != "ROTTEN" else 0.95,
                "SPROUTED": 0.05,
                "UNKNOWN": 0.10,
            },
            "diameter_mm": selected["diameter_mm"],
            "diameter_pixels": 160.0,
            "measurement_status": "measured",
            "pixels_per_mm": 3.2,
            "calibration_method": "demo_mode",
            "calibration_confidence": 0.92,
            "image_quality_passed": True,
        }]

        _, result_rows = GradingPersistenceService.evaluate_and_persist_inspection(
            db=db,
            inspection_id=inspection_id,
            observations_data=observations,
            policy_version_str="1.0.0",
            model_version_str="classifier-v1.0.0",
            actor_id=actor_id,
        )

        inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
        inspection.decision_reason = selected["reason"]
        inspection.status = "REVIEW_REQUIRED" if any(r.requires_review for r in result_rows) else "COMPLETED"
        db.commit()

        AuditService.log_event(
            db=db,
            actor_id=actor_id,
            action="AI_DEMO_GRADING",
            entity_type="Inspection",
            entity_id=inspection.id,
            new_values={
                "mode": "AI Demo Mode",
                "outcome": result_rows[0].grade if result_rows else demo_outcome.upper(),
                "reason": selected["reason"],
            },
        )
        db.commit()
        return result_rows

    @staticmethod
    def finalize_inspection(
        db: Session,
        inspection_id: str,
        actor_id: str,
    ) -> Report:
        """
        Finalizes inspection and generates tamper-evident Report with QR hash.
        """
        inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
        if not inspection:
            raise ValueError(f"Inspection '{inspection_id}' not found.")

        # Check existing report
        existing_report = db.query(Report).filter(Report.inspection_id == inspection_id).first()
        if existing_report:
            return existing_report

        report_code = f"REP-{inspection.inspection_code}"
        
        # SHA256 verifiable hash of inspection code + decision + timestamp
        now = datetime.now(timezone.utc)
        raw_hash_str = f"{inspection.id}:{inspection.inspection_code}:{inspection.lot_decision}:{now.isoformat()}"
        qr_hash = hashlib.sha256(raw_hash_str.encode("utf-8")).hexdigest()

        summary_metrics = {
            "total_onions": inspection.total_onions_evaluated,
            "grade_a_percentage": inspection.grade_a_percentage,
            "urs_percentage": inspection.urs_percentage,
            "reject_percentage": inspection.reject_percentage,
            "lot_decision": inspection.lot_decision,
            "decision_reason": inspection.decision_reason,
            "finalized_at": now.isoformat(),
        }

        report = Report(
            report_code=report_code,
            inspection_id=inspection.id,
            qr_verification_hash=qr_hash,
            summary_metrics=summary_metrics,
            is_finalized=True,
            generated_at=now,
        )
        db.add(report)
        db.flush()

        inspection.status = "COMPLETED"
        inspection.finalized_at = now

        AuditService.log_event(
            db=db,
            actor_id=actor_id,
            action="FINALIZE_INSPECTION_REPORT",
            entity_type="Report",
            entity_id=report.id,
            new_values={"report_code": report_code, "qr_hash": qr_hash},
        )

        db.commit()
        db.refresh(report)
        return report
