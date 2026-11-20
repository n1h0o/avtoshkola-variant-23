from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    BookingConfirmForm,
    ContactForm,
    DrivingRecordForm,
    ExamRequestForm,
    SlotCreateForm,
    SlotSearchForm,
    TheoryResultForm,
)
from .models import (
    ChangeLog,
    DrivingRecord,
    Employee,
    InstructorSlot,
    InternalExam,
    Notification,
    PracticeBooking,
    Student,
    TrainingLocation,
    TrainingProgram,
    TrainingVehicle,
)


def employee_role(role):
    # перед открытием служебной страницы проверяем роль и активность сотрудника.
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(request, *args, **kwargs):
            employee = getattr(request.user, "employee_profile", None)
            if not employee or employee.role != role or not employee.is_active:
                messages.error(
                    request, "У вашей учётной записи нет доступа к этому разделу."
                )
                return redirect("login")
            return view(request, employee, *args, **kwargs)

        return wrapped

    return decorator


def student_profile(request):
    return get_object_or_404(
        Student.objects.select_related("user", "program__category", "group"),
        user=request.user,
        is_active=True,
    )


def student_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        student = getattr(request.user, "student_profile", None)
        if not student or not student.is_active:
            messages.error(request, "Этот раздел доступен курсантам.")
            return redirect("login")
        return view(request, student, *args, **kwargs)

    return wrapped


@login_required
def home(request):
    if hasattr(request.user, "student_profile"):
        return redirect("student_dashboard")
    employee = getattr(request.user, "employee_profile", None)
    if employee:
        return redirect(
            {
                Employee.Role.INSTRUCTOR: "instructor_dashboard",
                Employee.Role.TEACHER: "teacher_dashboard",
                Employee.Role.ADMIN: "admin_dashboard",
            }[employee.role]
        )
    return redirect("login")


def logout_view(request):
    logout(request)
    return redirect("login")


@student_required
def student_dashboard(request, student):
    next_booking = (
        student.bookings.filter(
            status=PracticeBooking.Status.ACTIVE, slot__starts_at__gte=timezone.now()
        )
        .select_related("slot__instructor__user", "slot__vehicle", "slot__location")
        .first()
    )
    notices = request.user.school_notifications.all()[:3]
    return render(
        request,
        "school/student_dashboard.html",
        {"student": student, "next_booking": next_booking, "notices": notices},
    )


@student_required
def student_profile_page(request, student):
    form = ContactForm(
        request.POST or None,
        initial={"email": request.user.email, "phone": student.phone},
    )
    if request.method == "POST" and form.is_valid():
        request.user.email = form.cleaned_data["email"]
        request.user.save(update_fields=["email"])
        student.phone = form.cleaned_data["phone"]
        student.save(update_fields=["phone"])
        messages.success(request, "Контактные данные обновлены.")
        return redirect("student_profile")
    return render(request, "school/profile.html", {"student": student, "form": form})


def slot_queryset(student):
    # курсант видит только будущие свободные слоты для своей программы.
    return InstructorSlot.objects.filter(
        status=InstructorSlot.Status.AVAILABLE,
        starts_at__gte=timezone.now(),
        vehicle__category=student.program.category,
        vehicle__gearbox=student.program.gearbox,
        vehicle__is_active=True,
        instructor__is_active=True,
    ).select_related("instructor__user", "vehicle", "location")


@student_required
def schedule_data(request, student):
    slots = slot_queryset(student)
    raw_date = request.GET.get("date", "").strip()
    instructor = request.GET.get("instructor", "").strip()
    if raw_date:
        slots = slots.filter(starts_at__date=raw_date)
    if instructor.isdigit():
        slots = slots.filter(instructor_id=int(instructor))
    page = Paginator(slots, 20).get_page(request.GET.get("page", 1))
    items = [
        {
            "id": slot.pk,
            "start": timezone.localtime(slot.starts_at).strftime("%d.%m.%Y, %H:%M"),
            "date": timezone.localtime(slot.starts_at).date().isoformat(),
            "instructor": slot.instructor.user.get_full_name(),
            "vehicle": slot.vehicle.brand_model,
            "gearbox": slot.vehicle.gearbox,
            "location": slot.location.name,
            "url": reverse("slot_detail", args=[slot.pk]),
        }
        for slot in page.object_list
    ]
    return JsonResponse(
        {
            "items": items,
            "count": page.paginator.count,
            "page": page.number,
            "pages": page.paginator.num_pages,
            "has_next": page.has_next(),
        }
    )


@student_required
def schedule(request, student):
    form = SlotSearchForm(request.GET or None)
    instructors = Employee.objects.filter(role=Employee.Role.INSTRUCTOR, is_active=True)
    page = Paginator(slot_queryset(student), 20).get_page(request.GET.get("page", 1))
    return render(
        request,
        "school/schedule.html",
        {
            "student": student,
            "form": form,
            "instructors": instructors,
            "slots": page.object_list,
            "page_obj": page,
        },
    )


@student_required
def slot_detail(request, student, slot_id):
    slot = get_object_or_404(
        InstructorSlot.objects.select_related(
            "instructor__user", "vehicle", "location"
        ),
        pk=slot_id,
    )
    if (
        slot.vehicle.category_id != student.program.category_id
        or slot.vehicle.gearbox != student.program.gearbox
    ):
        messages.error(request, "Автомобиль не соответствует вашей учебной программе.")
        return redirect("schedule")
    form = BookingConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if slot.duration_minutes / 60 > student.remaining_hours:
            form.add_error(
                None, "Остатка практических часов недостаточно для этого занятия."
            )
        else:
            try:
                # блокировка слота не позволяет двум курсантам занять одно время.
                with transaction.atomic():
                    locked = InstructorSlot.objects.select_for_update().get(pk=slot.pk)
                    if (
                        locked.status != InstructorSlot.Status.AVAILABLE
                        or locked.starts_at <= timezone.now()
                    ):
                        form.add_error(
                            None,
                            "Это время уже занято. Обновите расписание и выберите другой слот.",
                        )
                    else:
                        booking = PracticeBooking.objects.create(
                            student=student, slot=locked
                        )
                        locked.status = InstructorSlot.Status.BOOKED
                        locked.save(update_fields=["status"])
                        Notification.objects.create(
                            recipient=request.user,
                            booking=booking,
                            message=f"Занятие забронировано на {timezone.localtime(locked.starts_at):%d.%m.%Y в %H:%M}.",
                        )
                        messages.success(request, "Занятие успешно забронировано.")
                        return redirect("bookings")
            except (IntegrityError, InstructorSlot.DoesNotExist):
                form.add_error(None, "Это время уже занято. Выберите другой слот.")
    return render(
        request,
        "school/slot_detail.html",
        {"student": student, "slot": slot, "form": form},
    )


@student_required
def bookings(request, student):
    items = student.bookings.select_related(
        "slot__instructor__user", "slot__vehicle", "slot__location"
    ).all()
    return render(
        request,
        "school/bookings.html",
        {"student": student, "bookings": items, "now": timezone.now()},
    )


@student_required
@require_POST
def cancel_booking(request, student, booking_id):
    booking = get_object_or_404(
        PracticeBooking.objects.select_related("slot"),
        pk=booking_id,
        student=student,
        status=PracticeBooking.Status.ACTIVE,
    )
    if booking.slot.starts_at <= timezone.now():
        messages.error(request, "Прошедшее занятие нельзя отменить через сайт.")
    else:
        booking.status = PracticeBooking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancel_reason = request.POST.get("reason", "Отменено курсантом")[:250]
        booking.save(update_fields=["status", "cancelled_at", "cancel_reason"])
        booking.slot.status = InstructorSlot.Status.AVAILABLE
        booking.slot.save(update_fields=["status"])
        ChangeLog.objects.create(
            booking=booking, changed_by=request.user, reason=booking.cancel_reason
        )
        Notification.objects.create(
            recipient=request.user,
            booking=booking,
            message="Бронь отменена, слот снова доступен.",
        )
        messages.success(request, "Бронь отменена.")
    return redirect("bookings")


@student_required
def progress(request, student):
    records = student.driving_records.select_related("instructor__user").all()
    return render(
        request, "school/progress.html", {"student": student, "records": records}
    )


@student_required
def exam(request, student):
    current = student.internal_exams.first()
    theory_ok = bool(current and current.theory_passed)
    # для запроса экзамена нужна сданная теория и не менее 90 процентов практики.
    practice_ok = student.practice_percent >= 90
    form = ExamRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not theory_ok or not practice_ok:
            missing = []
            if not theory_ok:
                missing.append("теоретический зачёт")
            if not practice_ok:
                missing.append("не менее 90% практики")
            messages.error(
                request,
                "Запись пока недоступна: необходимо выполнить условие - "
                + " и ".join(missing)
                + ".",
            )
        elif not current.exam_date:
            current.exam_date = form.cleaned_data["exam_date"]
            current.admission_status = "requested"
            current.save(update_fields=["exam_date", "admission_status"])
            messages.success(request, "Заявка на внутренний экзамен отправлена.")
            return redirect("exam")
        else:
            messages.info(request, "Заявка уже зарегистрирована.")
    return render(
        request,
        "school/exam.html",
        {
            "student": student,
            "exam_record": current,
            "theory_ok": theory_ok,
            "practice_ok": practice_ok,
            "form": form,
        },
    )


@employee_role(Employee.Role.INSTRUCTOR)
def instructor_dashboard(request, employee):
    slots = employee.slots.filter(starts_at__gte=timezone.now()).select_related(
        "vehicle", "location"
    )[:6]
    return render(
        request,
        "school/employee_dashboard.html",
        {
            "employee": employee,
            "slots": slots,
            "title": "Кабинет инструктора",
            "action_url": "instructor_slots",
            "action_label": "Расписание и слоты",
        },
    )


@employee_role(Employee.Role.INSTRUCTOR)
def instructor_slots(request, employee):
    form = SlotCreateForm(request.POST or None, instructor=employee)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.instructor = employee
        item.save()
        messages.success(request, "Слот добавлен в расписание.")
        return redirect("instructor_slots")
    slots = Paginator(
        employee.slots.select_related("vehicle", "location").all(), 20
    ).get_page(request.GET.get("page", 1))
    return render(
        request,
        "school/instructor_slots.html",
        {"employee": employee, "form": form, "slots": slots},
    )


@employee_role(Employee.Role.INSTRUCTOR)
def instructor_lessons(request, employee):
    form = DrivingRecordForm(request.POST or None, instructor=employee)
    if request.method == "POST" and form.is_valid():
        booking = form.cleaned_data["booking"]
        record = form.save(commit=False)
        record.student = booking.student
        record.instructor = employee
        record.save()
        booking.status = PracticeBooking.Status.COMPLETED
        booking.save(update_fields=["status"])
        booking.slot.status = InstructorSlot.Status.DONE
        booking.slot.save(update_fields=["status"])
        Notification.objects.create(
            recipient=booking.student.user,
            booking=booking,
            message=f"Практика за {record.duration_minutes} мин. внесена в историю.",
        )
        messages.success(request, "Проведённое занятие записано.")
        return redirect("instructor_lessons")
    records = (
        DrivingRecord.objects.filter(instructor=employee)
        .select_related("student__user")
        .all()[:25]
    )
    return render(
        request,
        "school/instructor_lessons.html",
        {"employee": employee, "form": form, "records": records},
    )


@employee_role(Employee.Role.TEACHER)
def teacher_dashboard(request, employee):
    form = TheoryResultForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exam_item = form.save(commit=False)
        exam_item.marked_by = employee
        exam_item.admission_status = "not_admitted"
        exam_item.save()
        messages.success(request, "Результат теоретического зачёта сохранён.")
        return redirect("teacher_dashboard")
    students = Student.objects.select_related("user", "program__category").all()
    return render(
        request,
        "school/teacher_dashboard.html",
        {"employee": employee, "form": form, "students": students},
    )


@employee_role(Employee.Role.ADMIN)
def admin_dashboard(request, employee):
    return render(
        request,
        "school/admin_dashboard.html",
        {
            "employee": employee,
            "student_count": Student.objects.count(),
            "employee_count": Employee.objects.count(),
            "slot_count": InstructorSlot.objects.count(),
            "booking_count": PracticeBooking.objects.count(),
            "programs": TrainingProgram.objects.select_related("category"),
            "vehicles": TrainingVehicle.objects.select_related("category"),
            "locations": TrainingLocation.objects.all(),
            "changes": ChangeLog.objects.select_related(
                "booking__student__user", "changed_by"
            )[:10],
        },
    )


@employee_role(Employee.Role.ADMIN)
def admin_users(request, employee):
    students = Student.objects.select_related("user", "program__category")
    staff = Employee.objects.select_related("user")
    return render(
        request,
        "school/admin_users.html",
        {"employee": employee, "students": students, "staff": staff},
    )


def about(request):
    return render(request, "school/about.html")
