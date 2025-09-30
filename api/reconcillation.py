from sqlalchemy.orm import Session
from typing import List

def get_all_hosts(db_session: Session) -> List[Host]:
    """
    Fetch all hosts from the database.
    
    Args:
        db_session (Session): SQLAlchemy session instance.
        
    Returns:
        List[Host]: List of Host objects.
    """
    return db_session.query(Host).all()
