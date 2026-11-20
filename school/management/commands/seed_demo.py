from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from school.models import (
    Category,
    DrivingRecord,
    Employee,
    InstructorSlot,
    InternalExam,
    Notification,
    PracticeBooking,
    Student,
    StudyGroup,
    TrainingLocation,
    TrainingProgram,
    TrainingVehicle,
)


class Command(BaseCommand):
    help = "Create synthetic demonstration accounts and driving school records."

    def handle(self, *args, **options):
        # команда создаёт демонстрационные данные и может запускаться повторно.
        User = get_user_model()
        cat_b, _ = Category.objects.get_or_create(
            code="B", defaults={"name": "Легковые автомобили"}
        )
        cat_a, _ = Category.objects.get_or_create(
            code="A", defaults={"name": "Мотоциклы"}
        )
        program_b, _ = TrainingProgram.objects.get_or_create(
            category=cat_b,
            gearbox="МКПП",
            defaults={"name": "B - механическая коробка", "practice_hours": 56},
        )
        program_auto, _ = TrainingProgram.objects.get_or_create(
            category=cat_b,
            gearbox="АКПП",
            defaults={"name": "B - автоматическая коробка", "practice_hours": 56},
        )
        program_a, _ = TrainingProgram.objects.get_or_create(
            category=cat_a,
            gearbox="МКПП",
            defaults={"name": "A - механическая коробка", "practice_hours": 18},
        )
        group, _ = StudyGroup.objects.get_or_create(
            code="ИСдо-45-демо",
            defaults={
                "category": cat_b,
                "start_date": date.today() - timedelta(days=60),
            },
        )
        loc, _ = TrainingLocation.objects.get_or_create(
            name="Учебная площадка № 1",
            defaults={"address": "Ульяновск, учебный автодром"},
        )

        def user_for(username, first_name, last_name, staff=False):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "is_staff": staff,
                },
            )
            user.first_name, user.last_name = first_name, last_name
            if staff and not user.is_staff:
                user.is_staff = True
            user.set_password("demo1234")
            user.save()
            return user

        student_user = user_for("kursant", "Иван", "Иванов")
        instructor_user = user_for("instructor", "Алексей", "Соколов")
        teacher_user = user_for("teacher", "Мария", "Петрова")
        admin_user = user_for("admin_demo", "Демо", "Администратор", staff=True)
        student, _ = Student.objects.get_or_create(
            user=student_user,
            defaults={
                "program": program_b,
                "group": group,
                "phone": "+7 900 000-00-01",
            },
        )
        instructor, _ = Employee.objects.get_or_create(
            user=instructor_user,
            defaults={"role": Employee.Role.INSTRUCTOR, "phone": "+7 900 000-00-02"},
        )
        Employee.objects.get_or_create(
            user=teacher_user,
            defaults={"role": Employee.Role.TEACHER, "phone": "+7 900 000-00-03"},
        )
        Employee.objects.get_or_create(
            user=admin_user,
            defaults={"role": Employee.Role.ADMIN, "phone": "+7 900 000-00-04"},
        )
        InternalExam.objects.get_or_create(
            student=student,
            marked_by=Employee.objects.get(user=teacher_user),
            defaults={
                "theory_passed": True,
                "theory_date": date.today() - timedelta(days=5),
            },
        )

        cars = []
        for number, gearbox, model in [
            (101, "МКПП", "Lada Granta"),
            (102, "АКПП", "Kia Rio"),
        ]:
            car, _ = TrainingVehicle.objects.get_or_create(
                registration_code=f"ДЕМО-{number}",
                defaults={"brand_model": model, "category": cat_b, "gearbox": gearbox},
            )
            cars.append(car)
        for i in range(1, 7):
            start = timezone.localtime(timezone.now()).replace(
                hour=9 + (i % 4) * 2, minute=0, second=0, microsecond=0
            ) + timedelta(days=i)
            InstructorSlot.objects.get_or_create(
                instructor=instructor,
                vehicle=cars[i % 2],
                location=loc,
                starts_at=start,
                defaults={"ends_at": start + timedelta(minutes=90)},
            )
        for i in range(1, 7):
            DrivingRecord.objects.get_or_create(
                student=student,
                instructor=instructor,
                actual_date=date.today() - timedelta(days=7 * i),
                duration_minutes=90,
                defaults={"comment": "Демонстрационная запись"},
            )
        next_manual = (
            InstructorSlot.objects.filter(
                status=InstructorSlot.Status.AVAILABLE,
                vehicle__gearbox=student.program.gearbox,
                starts_at__gt=timezone.now(),
            )
            .order_by("starts_at")
            .first()
        )
        if next_manual:
            booking, created = PracticeBooking.objects.get_or_create(
                student=student, slot=next_manual, status=PracticeBooking.Status.ACTIVE
            )
            if created:
                next_manual.status = InstructorSlot.Status.BOOKED
                next_manual.save(update_fields=["status"])
                Notification.objects.create(
                    recipient=student_user,
                    booking=booking,
                    message=f"Демонстрационная запись на {timezone.localtime(next_manual.starts_at):%d.%m.%Y в %H:%M}.",
                )
        self.stdout.write(
            self.style.SUCCESS(
                "Demo accounts ready. Logins: kursant, instructor, teacher, admin_demo. Password: demo1234"
            )
        )
