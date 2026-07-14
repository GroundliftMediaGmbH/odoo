{
    "name": "Groundlift Attendance Kiosk – White Text",
    "summary": "Makes employee and department labels readable on the Odoo Attendance kiosk.",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Attendances",
    "author": "Groundlift",
    "website": "https://groundlift.de",
    "license": "LGPL-3",
    "depends": ["hr_attendance"],
    "assets": {
        "hr_attendance.assets_public_attendance": [
            "groundlift_attendance_kiosk_white_text/static/src/scss/kiosk_white_text.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
