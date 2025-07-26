from sqlalchemy import UUID, Column, DateTime, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class IngestionStatus(Base):
    __tablename__ = 'ingestion_status'
    id = Column(UUID(as_uuid=True), primary_key=True)
    status = Column(Text)
    error_message= Column(Text)
    updated_at = Column(DateTime(), onupdate=func.now())
