import cloudinary.uploader
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor

class ArticleService:
    @staticmethod
    def upload_article_image(file, article_id):
        try:
            # الرفع إلى فولدر خاص بالمقالات hottiyya_articles
            result = cloudinary.uploader.upload(
                file,
                folder="hottiyya_articles",
                public_id=f"article_{article_id}",
                overwrite=True,
                resource_type="image"
            )
            return result.get("secure_url")
        except Exception as e:
            print(f"❌ Error uploading article image: {e}")
            return None

    @staticmethod
    def create_article(title, content, author_id, image_file=None):
        with get_db_context() as conn:
            with conn.cursor() as cur:
                # 1. حفظ المقال أولاً بدون صورة
                cur.execute("""
                    INSERT INTO articles (title, content, author_id)
                    VALUES (%s, %s, %s) RETURNING id
                """, (title, content, author_id))
                article_id = cur.fetchone()[0]
                
                # 2. إذا وجد ملف صورة، ارفعه وحدث الرابط
                image_url = None
                if image_file:
                    image_url = ArticleService.upload_article_image(image_file, article_id)
                    if image_url:
                        cur.execute("UPDATE articles SET image_url = %s WHERE id = %s", (image_url, article_id))
                
                conn.commit()
                return article_id
    
    @staticmethod
    def get_all_articles(page=1, per_page=12):
        try:
            offset = (page - 1) * per_page
            with get_db_context() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            a.id, a.title, a.content, a.image_url, a.created_at,
                            u.username,
                            COUNT(c.id) as comments_count
                        FROM articles a
                        JOIN users u ON a.author_id = u.id
                        LEFT JOIN comments c ON c.article_id = a.id
                        GROUP BY a.id, u.username, a.image_url -- تأكد من وجود image_url هنا
                        ORDER BY a.created_at DESC
                        LIMIT %s OFFSET %s
                    """, (per_page, offset))
                    articles = cur.fetchall()
                    
                    # جلب العدد الإجمالي
                    cur.execute("SELECT COUNT(*) FROM articles")
                    total = cur.fetchone()["count"]
                    total_pages = (total + per_page - 1) // per_page

                    return articles, total_pages
        except Exception as e:
            print(f"❌ Error in get_all_articles: {e}")
            return [], 0