from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class GoogleService:
    @staticmethod
    def get_all_sitemap_urls(base_url: str):
        pages = []
        try:
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. جلب روابط المقالات
                    cur.execute("SELECT id FROM articles ORDER BY created_at DESC")
                    for row in cur.fetchall():
                        pages.append({
                            "loc": f"{base_url}/articles/{row['id']}",
                            "changefreq": "weekly",
                            "priority": "0.6"
                        })
                    
                    # 2. جلب روابط الأخبار
                    cur.execute("SELECT id FROM news ORDER BY created_at DESC")
                    for row in cur.fetchall():
                        pages.append({
                            "loc": f"{base_url}/news/{row['id']}",
                            "changefreq": "weekly",
                            "priority": "0.6"
                        })
                        # 3. روابط الكتب في المكتبة (الإضافة الجديدة)
                        cur.execute("SELECT id FROM library WHERE status = 'approved' ORDER BY created_at DESC")
                        for row in cur.fetchall():
                            pages.append({
                                "loc": f"{base_url}/library/book/{row['id']}", 
                                "changefreq": "monthly", 
                                "priority": "0.5"
                            })
            return pages
        except Exception as e:
            print(f"❌ خطأ في جلب روابط Sitemap: {e}")
            return []