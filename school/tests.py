# проверки основных пользовательских сценариев приложения.
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Category,
    Employee,
    InstructorSlot,
    InternalExam,
    Student,
    StudyGroup,
    TrainingLocation,
    TrainingProgram,
    TrainingVehicle,
)


class SchoolFlowTests(TestCase):
    # набор тестов для ключевых сценариев обучения и записи.
    @classmethod
    def setUpTestData(cls):
        # создаёт общие тестовые аккаунты, программу и расписание.
        User = get_user_model()
        cls.cat_b = Category.objects.create(code="B", name="Легковые автомобили")
        cls.cat_a = Category.objects.create(code="A", name="Мотоциклы")
        cls.manual = TrainingProgram.objects.create(
            category=cls.cat_b, name="B МКПП", gearbox="МКПП", practice_hours=56
        )
        cls.auto = TrainingProgram.objects.create(
            category=cls.cat_b, name="B АКПП", gearbox="АКПП", practice_hours=56
        )
        group = StudyGroup.objects.create(
            code="TEST-1", category=cls.cat_b, start_date=timezone.localdate()
        )
        cls.student_user = User.objects.create_user(
            "test_student", password="test-pass", first_name="Тест", last_name="Курсант"
        )
        cls.student = Student.objects.create(
            user=cls.student_user,
            program=cls.manual,
            group=group,
            phone="+7 900 111-11-11",
        )
        cls.instructor_user = User.objects.create_user(
            "test_instructor",
            password="test-pass",
            first_name="Тест",
            last_name="Инструктор",
        )
        cls.instructor = Employee.objects.create(
            user=cls.instructor_user,
            role=Employee.Role.INSTRUCTOR,
            phone="+7 900 222-22-22",
        )
        cls.teacher_user = User.objects.create_user(
            "test_teacher",
            password="test-pass",
            first_name="Тест",
            last_name="Преподаватель",
        )
        cls.teacher = Employee.objects.create(
            user=cls.teacher_user, role=Employee.Role.TEACHER, phone="+7 900 333-33-33"
        )
        cls.admin_user = User.objects.create_user(
            "test_admin",
            password="test-pass",
            first_name="Тест",
            last_name="Администратор",
        )
        Employee.objects.create(
            user=cls.admin_user, role=Employee.Role.ADMIN, phone="+7 900 444-44-44"
        )
        location = TrainingLocation.objects.create(
            name="Тестовая площадка", address="Ульяновск"
        )
        manual_car = TrainingVehicle.objects.create(
            registration_code="TEST-M1",
            brand_model="Учебный автомобиль МКПП",
            category=cls.cat_b,
            gearbox="МКПП",
        )
        cls.manual_car = manual_car
        cls.location = location
        auto_car = TrainingVehicle.objects.create(
            registration_code="TEST-A1",
            brand_model="Учебный автомобиль АКПП",
            category=cls.cat_b,
            gearbox="АКПП",
        )
        future = timezone.now() + timedelta(days=2)
        cls.manual_slot = InstructorSlot.objects.create(
            instructor=cls.instructor,
            vehicle=manual_car,
            location=location,
            starts_at=future,
            ends_at=future + timedelta(minutes=90),
        )
        cls.auto_slot = InstructorSlot.objects.create(
            instructor=cls.instructor,
            vehicle=auto_car,
            location=location,
            starts_at=future + timedelta(days=1),
            ends_at=future + timedelta(days=1, minutes=90),
        )
        InternalExam.objects.create(
            student=cls.student,
            marked_by=cls.teacher,
            theory_passed=True,
            theory_date=timezone.localdate(),
        )

    def test_student_pages_require_login_and_load(self):
        # проверяет доступ курсанта к защищённым страницам.
        self.assertRedirects(
            self.client.get(reverse("student_dashboard")),
            f"{reverse('login')}?next={reverse('student_dashboard')}",
        )
        self.client.force_login(self.student_user)
        for name in (
            "student_dashboard",
            "student_profile",
            "schedule",
            "bookings",
            "progress",
            "exam",
        ):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200, name)

    def test_schedule_json_only_returns_vehicle_matching_program(self):
        # проверяет фильтр транспорта по программе курсанта.
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("schedule_data"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.json()["items"]], [self.manual_slot.id]
        )

    def test_schedule_json_paginates_by_twenty(self):
        # проверяет размер страницы в выдаче расписания.
        start = timezone.now() + timedelta(days=5)
        for i in range(20):
            slot_start = start + timedelta(days=i)
            InstructorSlot.objects.create(
                instructor=self.instructor,
                vehicle=self.manual_car,
                location=self.location,
                starts_at=slot_start,
                ends_at=slot_start + timedelta(minutes=90),
            )
        self.client.force_login(self.student_user)
        first = self.client.get(reverse("schedule_data"))
        self.assertEqual(first.json()["count"], 21)
        self.assertEqual(len(first.json()["items"]), 20)
        self.assertTrue(first.json()["has_next"])
        second = self.client.get(reverse("schedule_data"), {"page": 2})
        self.assertEqual(len(second.json()["items"]), 1)

    def test_student_can_book_matching_slot(self):
        # проверяет успешную запись на подходящий автомобиль.
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("slot_detail", args=[self.manual_slot.id]), {"confirm": "on"}
        )
        self.assertRedirects(response, reverse("bookings"))
        self.manual_slot.refresh_from_db()
        self.assertEqual(self.manual_slot.status, InstructorSlot.Status.BOOKED)
        self.assertEqual(self.student.bookings.count(), 1)

    def test_cancel_reopens_slot_and_writes_change_log(self):
        # проверяет отмену брони и освобождение слота.
        self.client.force_login(self.student_user)
        self.client.post(
            reverse("slot_detail", args=[self.manual_slot.id]), {"confirm": "on"}
        )
        booking = self.student.bookings.get(status="active")
        response = self.client.post(
            reverse("cancel_booking", args=[booking.id]), {"reason": "Проверка отмены"}
        )
        self.assertRedirects(response, reverse("bookings"))
        booking.refresh_from_db()
        self.manual_slot.refresh_from_db()
        self.assertEqual(booking.status, "cancelled")
        self.assertEqual(self.manual_slot.status, InstructorSlot.Status.AVAILABLE)
        self.assertEqual(booking.changes.count(), 1)

    def test_student_cannot_open_slot_with_wrong_gearbox(self):
        # проверяет запрет записи на неподходящую коробку передач.
        self.client.force_login(self.student_user)
        response = self.client.get(reverse("slot_detail", args=[self.auto_slot.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.student.bookings.count(), 0)

    def test_exam_request_is_blocked_before_practice_threshold(self):
        # проверяет ограничение допуска к экзамену.
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("exam"),
            {"exam_date": (timezone.localdate() + timedelta(days=10)).isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        current = self.student.internal_exams.first()
        self.assertIsNone(current.exam_date)
        self.assertTrue(response.context["messages"])

    def test_contact_form_rejects_invalid_phone(self):
        # проверяет отказ формы для некорректного телефона.
        self.client.force_login(self.student_user)
        response = self.client.post(
            reverse("student_profile"), {"phone": "123", "email": "bad"}
        )
        self.assertEqual(response.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, "+7 900 111-11-11")

    def test_employee_role_pages_load(self):
        # проверяет кабинеты сотрудника для каждой роли.
        self.client.force_login(self.instructor_user)
        self.assertEqual(
            self.client.get(reverse("instructor_dashboard")).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("instructor_slots")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("instructor_lessons")).status_code, 200
        )
        self.client.force_login(self.teacher_user)
        self.assertEqual(self.client.get(reverse("teacher_dashboard")).status_code, 200)
        self.client.force_login(self.admin_user)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_users")).status_code, 200)

    def test_login_redirects_employee_to_role_dashboard(self):
        # проверяет переход сотрудника в кабинет своей роли.
        response = self.client.post(
            reverse("login"),
            {"username": "test_instructor", "password": "test-pass"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.redirect_chain[-1][0], reverse("instructor_dashboard")
        )
