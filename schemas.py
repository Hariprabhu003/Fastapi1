# schemas.py
from pydantic import BaseModel

# Pydantic model for student creation
class StudentCreate(BaseModel):
    student_name: str
    teacher_id: int
class TeacherUpdate(BaseModel):
    teacher_name: str