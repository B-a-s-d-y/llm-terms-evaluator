from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

from python_script.evaluator import evaluate_policy

global_progress = 0

class TextHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS, GET')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path == '/progress':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps({"progress": global_progress}).encode('utf-8'))

    def do_POST(self):
        global global_progress
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            text = data.get('text', '')
            action = data.get('action', 'privacy')  # privacy 或 tos
            mode = 'sec' if action == 'privacy' else 'cont'
            force = data.get('force', False)
            page_title = data.get('title', '未知页面')
            page_url = data.get('url', '未知URL')
            
            # 每次收到新的分析请求重置进度
            global_progress = 0
            def prog_cb(curr, total):
                global global_progress
                global_progress = curr

            print(f"\n==================================================")
            print(f"收到分析请求: [{page_title}] ({page_url})")
            print(f"模式: {mode}, 文本长度: {len(text)}")
            print(f"==================================================")

            # 传入回调获取进度，并支持强制执行参数
            result = evaluate_policy(text, mode=mode, progress_callback=prog_cb, force=force, page_title=page_title, page_url=page_url)
            
            # 返回提取到的分析 JSON
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            print("解析错误/运行异常:", e)
            self.send_response(400)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            
    def log_message(self, format, *args):
        pass

def run(server_class=ThreadingHTTPServer, handler_class=TextHandler, port=8000):
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f'Starting Python Evaluator on http://localhost:{port}...')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == '__main__':
    run()

