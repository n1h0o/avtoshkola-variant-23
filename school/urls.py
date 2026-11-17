from django.urls import path

from . import views

urlpatterns = [
    path("about/", views.about, name="about"),
    path("", views.home, name="home"),
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("student/profile/", views.student_profile_page, name="student_profile"),
    path("student/schedule/", views.schedule, name="schedule"),
    path("student/schedule/data/", views.schedule_data, name="schedule_data"),
    path("student/schedule/slot/<int:slot_id>/", views.slot_detail, name="slot_detail"),
    path("student/bookings/", views.bookings, name="bookings"),
    path(
        "student/bookings/<int:booking_id>/cancel/",
        views.cancel_booking,
        name="cancel_booking",
    ),
    path("student/progress/", views.progress, name="progress"),
    path("student/exam/", views.exam, name="exam"),
    path("instructor/", views.instructor_dashboard, name="instructor_dashboard"),
    path("instructor/slots/", views.instructor_slots, name="instructor_slots"),
    path("instructor/lessons/", views.instructor_lessons, name="instructor_lessons"),
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("admin-panel/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-panel/users/", views.admin_users, name="admin_users"),
]
