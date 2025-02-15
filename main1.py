from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import pandas as pd
from database import SessionLocal
from database import  get_db
from models1 import Teacher, Student
from fastapi import HTTPException
from sqlalchemy import update
import schemas
import models1
import database

app = FastAPI()

print("Hiiii---------------")





@app.get("/teacher/{teacher_id}")
async def get_teacher_students(teacher_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Teacher.teacher_name, Student.student_name).join(Student, Teacher.teacher_id == Student.teacher_id).where(Teacher.teacher_id == teacher_id)
    result = await db.execute(query)
    data = result.fetchall()

    df = pd.DataFrame(data, columns=["teacher_name", "student_name"])

    return df.to_dict(orient="records")

@app.put("/teachers/{teacher_id}")
async def update_teacher(
    teacher_id: int,
    teacher: schemas.TeacherUpdate,
    db: AsyncSession = Depends(get_db)
):
    # Check if the teacher exists
    result = await db.execute(select(models1.Teacher.teacher_id).where(models1.Teacher.teacher_id == teacher_id))
    if result.scalar() is None:
        raise HTTPException(status_code=404, detail="Teacher not found")

    # Create and execute the update query
    query = (
        update(models1.Teacher)
        .where(models1.Teacher.teacher_id == teacher_id)
        .values(teacher_name=teacher.teacher_name)
    )
    await db.execute(query)

    # Commit the changes
    await db.commit()

    return {"message": "Teacher updated successfully"}

@app.delete("/students/{student_id}")
async def delete_student(student_id: int, db: AsyncSession = Depends(database.get_db)):
    # Fetch student to check if exists
    result = await db.execute(select(models1.Student).filter(models1.Student.student_id == student_id))
    db_student = result.scalars().first()

    if db_student is None:
        raise HTTPException(status_code=404, detail="Student not found")

    # Delete the student asynchronously
    await db.delete(db_student)

    # Commit changes
    await db.commit()

    return {"message": "Student deleted successfully"}


@app.post("/teacher_add")
async def create_teacher (name: str=None, db: AsyncSession = Depends(get_db)):
    new_teacher = Teacher(teacher_name=name)

    db.add(new_teacher)
    await db.commit()
    await db.refresh(new_teacher)

    return {"message": "Teacher created successfully", "teacher_name": new_teacher.teacher_name,
            "teacher_id": new_teacher.teacher_id}


@app.post("/insert_teachers/")
async def insert_teachers_api (  db: AsyncSession = Depends(get_db)):
    try:


        # Read the Excel file into a DataFrame
        contents = await file.read()
        df = pd.read_excel('teacher.xlsx')
        df.to_sql(teachers, engine, if_exists='append', index=False)

    except Exception as e:
        print(f"Error: {e}")

        return ("message : Table is inserted")