from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy import Column, Integer, String, ForeignKey
import pandas as pd

# DATABASE_URL = "postgresql+asyncpg://postgres:newpassword@localhost:5434/prabhu"
#
# engine = create_async_engine(DATABASE_URL, echo=True)
# SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class Teacher(Base):
    __tablename__ = "teachers"
    teacher_id = Column(Integer, primary_key=True, index=True)
    teacher_name = Column(String, index=True)

class Student(Base):
    __tablename__ = "students"
    student_id = Column(Integer, primary_key=True, index=True)
    student_name = Column(String, index=True)
    student_mobile = Column(String, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.teacher_id"))