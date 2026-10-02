"""
Database Initial Seeder for ONION_SURE
SIH 2026 PS26031 | Department of Consumer Affairs

Seeds default roles, admin/inspector/operator users, procurement centres,
farmers, grading policies, model versions, and initial sample lots.
"""

import logging
from sqlalchemy.orm import Session
from .models.entities import (
    User,
    Role,
    UserRole,
    ProcurementCentre,
    Farmer,
    Lot,
    Inspection,
    GradingPolicy,
    GradingPolicyVersion,
    ModelVersion,
)
from .security import hash_password

logger = logging.getLogger("onion_sure.seed")


def seed_database(db: Session) -> None:
    """Idempotently seeds all core reference data and demo accounts."""
    # 1. Roles
    roles = {
        "SUPER_ADMIN": "System administrator with full privileges",
        "CENTRE_ADMIN": "Procurement centre administrator",
        "OPERATOR": "Data entry and lot intake operator",
        "AUDITOR": "Quality assurance reviewer and verifier",
        "INSPECTOR": "Quality inspector performing lot assessments",
        "OFFICER": "Procurement / mandi nodal officer",
        "REVIEWER": "Legacy reviewer alias for manual overrides",
        "ADMIN": "Legacy administrator alias",
    }
    role_objs = {}
    for r_name, r_desc in roles.items():
        role = db.query(Role).filter_by(name=r_name).first()
        if not role:
            role = Role(name=r_name, description=r_desc)
            db.add(role)
            db.flush()
        role_objs[r_name] = role

    # 2. Procurement Centres
    centre = db.query(ProcurementCentre).filter_by(centre_code="PC-MH-NSK-001").first()
    if not centre:
        centre = ProcurementCentre(
            centre_code="PC-MH-NSK-001",
            name="Lasalgaon APMC Mandi Hub",
            district="Nashik",
            state="Maharashtra",
            is_active=True,
        )
        db.add(centre)
        db.flush()

    # 3. Default Users
    default_users = [
        {
            "email": "superadmin@onionsure.gov.in",
            "full_name": "System Administrator",
            "password": "Admin@12345",
            "role": "SUPER_ADMIN",
            "is_superuser": True,
        },
        {
            "email": "admin@onionsure.gov.in",
            "full_name": "Legacy Administrator",
            "password": "Admin@12345",
            "role": "ADMIN",
            "is_superuser": True,
        },
        {
            "email": "centreadmin@onionsure.gov.in",
            "full_name": "Centre Admin",
            "password": "CentreAdmin@12345",
            "role": "CENTRE_ADMIN",
            "is_superuser": False,
        },
        {
            "email": "inspector@onionsure.gov.in",
            "full_name": "Senior Quality Inspector",
            "password": "Inspector@12345",
            "role": "INSPECTOR",
            "is_superuser": False,
        },
        {
            "email": "operator@onionsure.gov.in",
            "full_name": "Intake Desk Operator",
            "password": "Operator@12345",
            "role": "OPERATOR",
            "is_superuser": False,
        },
        {
            "email": "auditor@onionsure.gov.in",
            "full_name": "Quality Audit Reviewer",
            "password": "Auditor@12345",
            "role": "AUDITOR",
            "is_superuser": False,
        },
        {
            "email": "reviewer@onionsure.gov.in",
            "full_name": "Legacy QA Reviewer",
            "password": "Reviewer@12345",
            "role": "REVIEWER",
            "is_superuser": False,
        },
    ]

    for u_info in default_users:
        user = db.query(User).filter_by(email=u_info["email"]).first()
        if not user:
            user = User(
                email=u_info["email"],
                full_name=u_info["full_name"],
                hashed_password=hash_password(u_info["password"]),
                procurement_centre_id=centre.id,
                is_active=True,
                is_superuser=u_info["is_superuser"],
            )
            db.add(user)
            db.flush()
            user_role = UserRole(user_id=user.id, role_id=role_objs[u_info["role"]].id)
            db.add(user_role)

    # 4. Model Version
    mv = db.query(ModelVersion).filter_by(version="1.0.0").first()
    if not mv:
        mv = ModelVersion(
            model_name="YOLOv8-Onion-Quality-Detector",
            version="1.0.0",
            model_type="yolo_detector",
            artifact_reference="models/yolov8_onion_best.pt",
            dataset_version="1.0.0",
            metrics_summary={"mAP50": 0.942, "precision": 0.915, "recall": 0.898, "f1_score": 0.906},
            status="ACTIVE",
        )
        db.add(mv)
        db.flush()

    # 5. Grading Policy
    gp = db.query(GradingPolicy).filter_by(code="DOCA-ONION-STD-2026").first()
    if not gp:
        gp = GradingPolicy(
            code="DOCA-ONION-STD-2026",
            name="DoCA National Onion Quality Standard (PS26031)",
            crop="Onion",
            is_active=True,
        )
        db.add(gp)
        db.flush()

        gpv = GradingPolicyVersion(
            policy_id=gp.id,
            version="1.0.0",
            configuration={
                "grade_a_min_percentage": 75.0,
                "max_defective_percentage": 10.0,
                "max_sprouting_percentage": 5.0,
                "max_undersized_percentage": 8.0,
                "min_diameter_mm": 45.0,
                "max_diameter_mm": 80.0,
                "allow_minor_blemishes": True,
            },
        )
        db.add(gpv)
        db.flush()

    # 6. Sample Farmers
    farmers_data = [
        {"farmer_code": "FMR-001", "name": "Ramesh Patil", "phone": "+91 98230 11223", "village": "Lasalgaon", "district": "Nashik", "state": "Maharashtra"},
        {"farmer_code": "FMR-002", "name": "Suresh Deshmukh", "phone": "+91 98221 44556", "village": "Baramati", "district": "Pune", "state": "Maharashtra"},
        {"farmer_code": "FMR-003", "name": "Anil Shinde", "phone": "+91 98229 77889", "village": "Rahata", "district": "Ahmednagar", "state": "Maharashtra"},
    ]
    farmer_objs = []
    for f_info in farmers_data:
        farmer = db.query(Farmer).filter_by(farmer_code=f_info["farmer_code"]).first()
        if not farmer:
            farmer = Farmer(**f_info)
            db.add(farmer)
            db.flush()
        farmer_objs.append(farmer)

    # 7. Sample Lots & Completed Inspections
    lot1 = db.query(Lot).filter_by(lot_number="LOT-2026-NSK-001").first()
    if not lot1 and farmer_objs:
        lot1 = Lot(
            lot_number="LOT-2026-NSK-001",
            farmer_id=farmer_objs[0].id,
            procurement_centre_id=centre.id,
            variety="Red Onion",
            quantity_quintals=45.5,
            bag_count=91,
            status="GRADED",
        )
        db.add(lot1)
        db.flush()

        insp_user = db.query(User).filter_by(email="inspector@onionsure.gov.in").first()
        if insp_user:
            insp = Inspection(
                inspection_code="INSP-2026-001",
                lot_id=lot1.id,
                inspector_id=insp_user.id,
                sample_size=120,
                status="COMPLETED",
                total_onions_evaluated=120,
                grade_a_count=102,
                grade_a_percentage=85.0,
                urs_count=14,
                urs_percentage=11.67,
                reject_count=4,
                reject_percentage=3.33,
                manual_review_count=0,
                lot_decision="ACCEPTABLE",
                decision_reason="Meets DoCA Grade A threshold (>75%)",
            )
            db.add(insp)

    lot2 = db.query(Lot).filter_by(lot_number="LOT-2026-NSK-002").first()
    if not lot2 and len(farmer_objs) > 1:
        lot2 = Lot(
            lot_number="LOT-2026-NSK-002",
            farmer_id=farmer_objs[1].id,
            procurement_centre_id=centre.id,
            variety="Red Onion",
            quantity_quintals=30.0,
            bag_count=60,
            status="INSPECTING",
        )
        db.add(lot2)

    lot3 = db.query(Lot).filter_by(lot_number="LOT-2026-PUN-003").first()
    if not lot3 and len(farmer_objs) > 2:
        lot3 = Lot(
            lot_number="LOT-2026-PUN-003",
            farmer_id=farmer_objs[2].id,
            procurement_centre_id=centre.id,
            variety="White Onion",
            quantity_quintals=65.0,
            bag_count=130,
            status="REGISTERED",
        )
        db.add(lot3)

    db.commit()
    logger.info("Database seeding completed successfully.")
