from django.conf import settings
from django.db import models
from django.db.models import Q


class Category(models.Model):
    code = models.CharField(max_length=2, unique=True)
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "категория"
        verbose_name_plural = "категории"

    def __str__(self):
        return f"{self.code} - {self.name}"


class TrainingProgram(models.Model):
    class Gearbox(models.TextChoices):
        MANUAL = "МКПП", "Механическая"
        AUTO = "АКПП", "Автоматическая"

    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="programs"
    )
    name = models.CharField(max_length=120)
    gearbox = models.CharField(max_length=4, choices=Gearbox.choices)
    practice_hours = models.PositiveSmallIntegerField(default=56)

    class Meta:
        ordering = ["category__code", "gearbox"]
        verbose_name = "программа обучения"
        verbose_name_plural = "программы обучения"

    def __str__(self):
        return f"{self.category.code} - {self.gearbox}"


class StudyGroup(models.Model):
    code = models.CharField(max_length=30, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="groups"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default="active")

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "учебная группа"
        verbose_name_plural = "учебные группы"

    def __str__(self):
        return self.code


class Student(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    program = models.ForeignKey(
        TrainingProgram, on_delete=models.PROTECT, related_name="students"
    )
    group = models.ForeignKey(
        StudyGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="students",
    )
    phone = models.CharField(max_length=20)
    enrolled_at = models.DateField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]
        verbose_name = "курсант"
        verbose_name_plural = "курсанты"

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def completed_minutes(self):
        return sum(item.duration_minutes for item in self.driving_records.all())

    @property
    def completed_hours(self):
        return self.completed_minutes / 60

    @property
    def remaining_hours(self):
        return max(float(self.program.practice_hours) - self.completed_hours, 0)

    @property
    def practice_percent(self):
        if not self.program.practice_hours:
            return 0
        return min(round(self.completed_hours / self.program.practice_hours * 100), 100)


class Employee(models.Model):
    class Role(models.TextChoices):
        INSTRUCTOR = "instructor", "Инструктор"
        TEACHER = "teacher", "Преподаватель"
        ADMIN = "admin", "Администратор"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    phone = models.CharField(max_length=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "сотрудник"
        verbose_name_plural = "сотрудники"

    def __str__(self):
        return f"{self.user.get_full_name()} - {self.get_role_display()}"


class TrainingVehicle(models.Model):
    registration_code = models.CharField(max_length=12, unique=True)
    brand_model = models.CharField(max_length=100)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="vehicles"
    )
    gearbox = models.CharField(max_length=4, choices=TrainingProgram.Gearbox.choices)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["registration_code"]
        verbose_name = "учебный автомобиль"
        verbose_name_plural = "учебные автомобили"

    def __str__(self):
        return f"{self.brand_model} - {self.gearbox} ({self.registration_code})"


class TrainingLocation(models.Model):
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=250)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "площадка"
        verbose_name_plural = "площадки"

    def __str__(self):
        return self.name


class InstructorSlot(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Свободно"
        BOOKED = "booked", "Забронировано"
        DONE = "done", "Проведено"
        CANCELLED = "cancelled", "Отменено"

    instructor = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="slots"
    )
    vehicle = models.ForeignKey(
        TrainingVehicle, on_delete=models.PROTECT, related_name="slots"
    )
    location = models.ForeignKey(
        TrainingLocation, on_delete=models.PROTECT, related_name="slots"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AVAILABLE
    )

    class Meta:
        ordering = ["starts_at"]
        verbose_name = "слот расписания"
        verbose_name_plural = "слоты расписания"
        constraints = [
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="slot_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.starts_at:%d.%m.%Y %H:%M} - {self.instructor}"

    @property
    def duration_minutes(self):
        return int((self.ends_at - self.starts_at).total_seconds() // 60)


class PracticeBooking(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        CANCELLED = "cancelled", "Отменена"
        COMPLETED = "completed", "Завершена"

    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="bookings"
    )
    slot = models.ForeignKey(
        InstructorSlot, on_delete=models.PROTECT, related_name="bookings"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["slot__starts_at"]
        verbose_name = "бронь"
        verbose_name_plural = "брони"
        constraints = [
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(status="active"),
                name="one_active_booking_per_slot",
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.slot.starts_at:%d.%m.%Y %H:%M}"


class DrivingRecord(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.PROTECT, related_name="driving_records"
    )
    booking = models.OneToOneField(
        PracticeBooking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="driving_record",
    )
    instructor = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="driving_records"
    )
    actual_date = models.DateField()
    duration_minutes = models.PositiveSmallIntegerField()
    comment = models.CharField(max_length=250, blank=True)

    class Meta:
        ordering = ["-actual_date"]
        verbose_name = "запись о практике"
        verbose_name_plural = "записи о практике"
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_minutes__gt=0), name="driving_duration_positive"
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.actual_date:%d.%m.%Y}, {self.duration_minutes} мин."


class InternalExam(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="internal_exams"
    )
    theory_passed = models.BooleanField(default=False)
    theory_date = models.DateField(null=True, blank=True)
    marked_by = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="theory_marks"
    )
    exam_date = models.DateField(null=True, blank=True)
    admission_status = models.CharField(max_length=30, default="not_admitted")

    class Meta:
        ordering = ["-id"]
        verbose_name = "допуск к экзамену"
        verbose_name_plural = "допуски к экзамену"

    def __str__(self):
        return f"{self.student} - {self.admission_status}"


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="school_notifications",
    )
    booking = models.ForeignKey(
        PracticeBooking,
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
    )
    message = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "уведомление"
        verbose_name_plural = "уведомления"

    def __str__(self):
        return self.message


class ChangeLog(models.Model):
    booking = models.ForeignKey(
        PracticeBooking, on_delete=models.CASCADE, related_name="changes"
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="booking_changes",
    )
    reason = models.CharField(max_length=250)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "изменение брони"
        verbose_name_plural = "журнал изменений"

    def __str__(self):
        return f"Бронь #{self.booking_id} - {self.reason}"
