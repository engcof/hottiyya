from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class GoogleService:
    # في ملف GoogleService
    @staticmethod
    def get_all_sitemap_urls(base_url: str):
        pages = []
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. المقالات
                    cur.execute("SELECT id FROM articles")
                    articles = cur.fetchall() # نجلبهم كلهم أولاً ونغلق الاستعلام
                    for row in articles:
                        pages.append({"loc": f"{base_url}/articles/{row['id']}", "changefreq": "weekly", "priority": "0.6"})
                    
                    # 2. الأخبار
                    cur.execute("SELECT id FROM news")
                    news = cur.fetchall()
                    for row in news:
                        pages.append({"loc": f"{base_url}/news/{row['id']}", "changefreq": "weekly", "priority": "0.6"})

                    # 3. المكتبة (تأكد أنها خارج الـ Loop السابقة)
                    cur.execute("SELECT id FROM library WHERE status = 'approved'")
                    books = cur.fetchall()
                    for row in books:
                        pages.append({"loc": f"{base_url}/library/book/{row['id']}", "changefreq": "monthly", "priority": "0.5"})
            return pages
        except Exception as e:
            print(f"❌ Sitemap Error: {e}")
            return []