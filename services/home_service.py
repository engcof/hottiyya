from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class HomeService:
    @classmethod
    def get_homepage_data(cls):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. جلب أحدث مقال
                cur.execute("SELECT id, title FROM articles ORDER BY created_at DESC LIMIT 1")
                latest_article = cur.fetchone()

                # 2. جلب أحدث كتاب (الاسم والصورة)
                # نفترض أن جدول الكتب اسمه books وبه حقل cover_image
                cur.execute("SELECT id, title, cover_url FROM library ORDER BY created_at DESC LIMIT 1")
                latest_book = cur.fetchone()

                return {
                    "latest_article": latest_article,
                    "latest_book": latest_book
                }