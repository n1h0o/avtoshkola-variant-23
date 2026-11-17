from django.contrib import admin

from .models import (Category, ChangeLog, DrivingRecord, Employee, InstructorSlot, InternalExam,
                     Notification, PracticeBooking, Student, StudyGroup, TrainingLocation,
                     TrainingProgram, TrainingVehicle)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("user", "program", "group", "phone", "is_active")
    list_filter = ("program__category", "program__gearbox", "is_active")
    search_fields = ("user__first_name", "user__last_name", "user__username")


@admin.register(InstructorSlot)
class InstructorSlotAdmin(admin.ModelAdmin):
    list_display = ("starts_at", "instructor", "vehicle", "location", "status")
    list_filter = ("status", "vehicle__gearbox", "vehicle__category")
    date_hierarchy = "starts_at"


@admin.register(PracticeBooking)
class PracticeBookingAdmin(admin.ModelAdmin):
    list_display = ("student", "slot", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("student__user__last_name", "student__user__first_name")


admin.site.register([Category, TrainingProgram, StudyGroup, Employee, TrainingVehicle,
                     TrainingLocation, DrivingRecord, InternalExam, Notification, ChangeLog])
