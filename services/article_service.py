# article_service.py
import cloudinary.uploader
from postgresql import get_db_context
from psycopg2.extras import RealDictCursor
import asyncio

class ArticleService:
   
    @staticmethod
    async def upload_article_image(image_file, article_id):
        try:
            # قراءة المحتوى بشكل غير متزامن
            file_content = await image_file.read()
            
            # ملاحظة: مكتبة Cloudinary الأصلية متزامنة، لذا يفضل تشغيلها في thread منفصل 
            # أو استدعاؤها مباشرة كما فعلت وهي ستعمل لكن await هنا للملف ضرورية
            upload_result = cloudinary.uploader.upload(
                file_content,
                folder="hottiyya_articles",
                public_id=f"article_{article_id}",
                overwrite=True,
                resource_type="image"
            )
            return upload_result.get("secure_url")
        except Exception as e:
            print(f"❌ خطأ في الرفع: {e}")
            return None
      
    @staticmethod
    async def create_article(title, content, author_id, image_file=None): # تحويل إلى async
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO articles (title, content, author_id)
                    VALUES (%s, %s, %s) RETURNING id
                """, (title, content, author_id))
                article_id = cur.fetchone()[0]
                
                image_url = None
                if image_file and image_file.filename:
                    # الآن يمكنك استخدام await لأن الدالة أصبحت async
                    image_url = await ArticleService.upload_article_image(image_file, article_id)
                    if image_url:
                        cur.execute("UPDATE articles SET image_url = %s WHERE id = %s", (image_url, article_id))
                
                conn.commit()
                return article_id

    @staticmethod
    async def update_article(article_id, title, content, image_file=None): # تحويل إلى async
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT image_url FROM articles WHERE id = %s", (article_id,))
                row = cur.fetchone()
                image_url = row[0] if row else None

                if image_file and image_file.filename:
                    new_url = await ArticleService.upload_article_image(image_file, article_id)
                    if new_url:
                        image_url = new_url

                cur.execute("""
                    UPDATE articles 
                    SET title = %s, content = %s, image_url = %s 
                    WHERE id = %s
                """, (title, content, image_url, article_id))
                conn.commit()
                return True
    
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
        
    @staticmethod
    def get_article_details(article_id):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # جلب المقال
                cur.execute("""
                    SELECT a.*, u.username FROM articles a 
                    JOIN users u ON a.author_id = u.id WHERE a.id = %s
                """, (article_id,))
                article = cur.fetchone()
                if not article: return None, []

                # جلب التعليقات
                cur.execute("""
                    SELECT c.*, u.username FROM comments c
                    JOIN users u ON c.user_id = u.id
                    WHERE c.article_id = %s ORDER BY c.created_at DESC
                """, (article_id,))
                comments = cur.fetchall()
                return article, comments
    
    @staticmethod
    def get_article_by_id(article_id):
        """جلب مقال محدد بواسطة المعرف"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM articles WHERE id = %s", (article_id,))
                return cur.fetchone()

    
    
    @staticmethod
    def delete_article(article_id):
        """حذف المقال وملفاته من السحابة والتعليقات المرتبطة به"""
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. جلب البيانات قبل الحذف
                cur.execute("SELECT image_url FROM articles WHERE id = %s", (article_id,))
                article = cur.fetchone()
                
                if not article:
                    return False

                # 2. حذف الصورة من Cloudinary
                image_url = article.get("image_url")
                if image_url and "cloudinary.com" in image_url:
                    try:
                        # استخراج اسم الملف البرمجي من الرابط
                        filename = image_url.split('/')[-1].split('.')[0]
                        public_id = f"hottiyya_articles/{filename}"
                        
                        cloudinary.uploader.destroy(public_id)
                        print(f"✅ تم حذف صورة المقال من السحابة: {public_id}")
                    except Exception as e:
                        print(f"⚠️ فشل حذف ملف السحابة: {e}")

                # 3. العمليات على قاعدة البيانات (التعليقات ثم المقال)
                cur.execute("DELETE FROM comments WHERE article_id = %s", (article_id,))
                cur.execute("DELETE FROM articles WHERE id = %s", (article_id,))
                
                conn.commit()
                return True
            
     

    @staticmethod
    def add_comment(article_id, user_id, content):
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO comments (article_id, user_id, content) 
                    VALUES (%s, %s, %s)
                """, (article_id, user_id, content))
                conn.commit()

    @staticmethod
    def get_comment_owner(comment_id):
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT user_id, content FROM comments WHERE id = %s", (comment_id,))
                return cur.fetchone()

    @staticmethod
    def delete_comment(comment_id):
        with get_db_context() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM comments WHERE id = %s", (comment_id,))
                conn.commit()

    @staticmethod
    def get_latest_article_id():
        with get_db_context() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id 
                    FROM articles 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """)
                latest = cur.fetchone()
                return latest['id'] if latest else None            