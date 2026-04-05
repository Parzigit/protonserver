# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
# import os

# DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://backenduser:backendpassword@localhost:5432/pdfsidekick")

# engine = create_engine(DATABASE_URL, future=True)
# SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)