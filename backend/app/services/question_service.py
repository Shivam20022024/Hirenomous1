import pandas as pd
import os
import logging

logger = logging.getLogger(__name__)

class QuestionService:
    _questions = None
    _file_path = "questions.xlsx"

    @classmethod
    def load_questions(cls):
        """Loads questions from the Excel file."""
        try:
            if not os.path.exists(cls._file_path):
                logger.error(f"Questions file not found at {cls._file_path}")
                return []
            
            df = pd.read_excel(cls._file_path)
            cls._questions = df.to_dict('records')
            logger.info(f"Loaded {len(cls._questions)} questions from {cls._file_path}")
            return cls._questions
        except Exception as e:
            logger.error(f"Error loading questions: {str(e)}")
            return []

    @classmethod
    def get_question(cls, index: int):
        """Returns a question by its index."""
        if cls._questions is None:
            cls.load_questions()
        
        if 0 <= index < len(cls._questions):
            return cls._questions[index]
        return None

    @classmethod
    def get_total_questions(cls):
        """Returns the total number of questions."""
        if cls._questions is None:
            cls.load_questions()
        return len(cls._questions)
