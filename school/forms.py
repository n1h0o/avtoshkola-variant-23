from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.utils import timezone
from django.db.models import Q

from .models import DrivingRecord, Employee, InstructorSlot, InternalExam, PracticeBooking, Student, TrainingVehicle


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "Ваш логин"}))
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Ваш пароль"}))


class BookingConfirmForm(forms.Form):
    confirm = forms.BooleanField(label="Подтверждаю выбранное время и автомобиль", required=True)


class SlotSearchForm(forms.Form):
    date = forms.DateField(required=False, label="Дата", widget=forms.DateInput(attrs={"type": "date"}))
    instructor = forms.ModelChoiceField(required=False, label="Инструктор", queryset=Employee.objects.filter(role=Employee.Role.INSTRUCTOR, is_active=True))


class ContactForm(forms.Form):
    email = forms.EmailField(label="Электронная почта", required=False, widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "name@example.com"}))
    phone = forms.CharField(label="Телефон", max_length=20, widget=forms.TelInput(attrs={"autocomplete": "tel", "placeholder": "+7 900 000-00-00"}))

    def clean_phone(self):
        import re
        value = self.cleaned_data["phone"].strip()
        digits = re.sub(r"\D", "", value)
        if not re.fullmatch(r"\+?[0-9()\-\s]{10,20}", value) or len(digits) < 10 or len(digits) > 15:
            raise forms.ValidationError("Введите телефон с кодом страны, например +7 900 000-00-00.")
        return value


class SlotCreateForm(forms.ModelForm):
    class Meta:
        model = InstructorSlot
        fields = ["vehicle", "location", "starts_at", "ends_at"]
        labels = {"vehicle": "Учебный автомобиль", "location": "Площадка", "starts_at": "Начало", "ends_at": "Окончание"}
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, instructor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instructor = instructor
        self.fields["vehicle"].queryset = TrainingVehicle.objects.filter(is_active=True)
        for field in ("starts_at", "ends_at"):
            self.fields[field].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("starts_at"), cleaned.get("ends_at")
        if start and end:
            if timezone.is_naive(start):
                start = timezone.make_aware(start, timezone.get_current_timezone())
                cleaned["starts_at"] = start
            if timezone.is_naive(end):
                end = timezone.make_aware(end, timezone.get_current_timezone())
                cleaned["ends_at"] = end
            if end <= start:
                self.add_error("ends_at", "Окончание должно быть позже начала.")
            if start <= timezone.now():
                self.add_error("starts_at", "Нельзя создать слот в прошлом.")
            if self.instructor:
                conflict = Q(instructor=self.instructor)
                if cleaned.get("vehicle"):
                    conflict |= Q(vehicle=cleaned["vehicle"])
                overlap = InstructorSlot.objects.filter(starts_at__lt=end, ends_at__gt=start).filter(conflict)
                if overlap.exists():
                    self.add_error(None, "У инструктора или автомобиля уже есть занятие в это время.")
        return cleaned


class DrivingRecordForm(forms.ModelForm):
    class Meta:
        model = DrivingRecord
        fields = ["booking", "actual_date", "duration_minutes", "comment"]
        labels = {"booking": "Бронь курсанта", "actual_date": "Фактическая дата", "duration_minutes": "Длительность, минут", "comment": "Комментарий"}
        widgets = {"actual_date": forms.DateInput(attrs={"type": "date"}), "comment": forms.Textarea(attrs={"rows": 2, "maxlength": 250})}

    def __init__(self, *args, instructor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["booking"].queryset = PracticeBooking.objects.filter(status=PracticeBooking.Status.ACTIVE, slot__instructor=instructor).select_related("student", "slot")
        self.fields["booking"].label_from_instance = lambda item: f"{item.student} - {item.slot.starts_at:%d.%m.%Y %H:%M}"
        self.fields["duration_minutes"].min_value = 1

    def clean_actual_date(self):
        actual_date = self.cleaned_data["actual_date"]
        if actual_date > timezone.localdate():
            raise forms.ValidationError("Дата занятия не может быть в будущем.")
        return actual_date


class TheoryResultForm(forms.ModelForm):
    class Meta:
        model = InternalExam
        fields = ["student", "theory_passed", "theory_date"]
        labels = {"student": "Курсант", "theory_passed": "Теоретический зачёт сдан", "theory_date": "Дата зачёта"}
        widgets = {"theory_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_active=True).select_related("user", "program")
        self.fields["student"].label_from_instance = lambda item: f"{item} - {item.program.category.code}"


class ExamRequestForm(forms.Form):
    exam_date = forms.DateField(label="Предпочтительная дата", widget=forms.DateInput(attrs={"type": "date"}))

    def clean_exam_date(self):
        value = self.cleaned_data["exam_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Дата не может быть в прошлом.")
        return value
