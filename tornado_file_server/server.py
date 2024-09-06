import tornado.ioloop
import tornado.web
import os
from datetime import datetime
import math
import argparse
from tornado.escape import url_escape
import mimetypes

import socket

# 转换文件大小为human-readable格式
def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.{decimal_places}f} {unit}"
        size /= 1024.0

# 获取文件类型
def get_file_type(file_path):
    if os.path.isdir(file_path):
        return 'Directory'
    else:
        return os.path.splitext(file_path)[1] or 'File'

# 获取文件信息
def get_file_info(folder_path):
    files_info = []
    try:
        for file_name in sorted(os.listdir(folder_path)):
            file_path = os.path.join(folder_path, file_name)
            if os.path.isdir(file_path) or os.path.isfile(file_path):
                stat_info = os.stat(file_path)
                files_info.append({
                    'name': file_name,
                    'size': stat_info.st_size,  # 保留字节大小，用于排序
                    'human_readable_size': human_readable_size(stat_info.st_size),  # 转换为可读大小
                    'creation_time': datetime.fromtimestamp(stat_info.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'modification_time': datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                    'type': get_file_type(file_path)
                })
    except Exception as e:
        print(f"Error accessing folder: {e}")
        raise tornado.web.HTTPError(404)
    return files_info

# 文件排序逻辑
def sort_files(files_info, sort_by, order):
    reverse = (order == 'desc')
    if sort_by == 'name':
        files_info.sort(key=lambda x: x['name'].lower(), reverse=reverse)
    elif sort_by == 'size':
        files_info.sort(key=lambda x: x['size'], reverse=reverse)
    elif sort_by == 'creation_time':
        files_info.sort(key=lambda x: x['creation_time'], reverse=reverse)
    elif sort_by == 'modification_time':
        files_info.sort(key=lambda x: x['modification_time'], reverse=reverse)
    elif sort_by == 'type':
        files_info.sort(key=lambda x: x['type'].lower(), reverse=reverse)

class MainHandler(tornado.web.RequestHandler):
    def get(self, subpath=''):
        folder_path = os.path.join(self.application.settings['root_folder'], subpath)
        if not os.path.exists(folder_path):
            raise tornado.web.HTTPError(404)

        sort_by = self.get_argument('sort_by', 'name')
        order = self.get_argument('order', 'asc')
        page = int(self.get_argument('page', 1))
        items_per_page = 100
        start = (page - 1) * items_per_page
        end = start + items_per_page

        files_info = get_file_info(folder_path)
        sort_files(files_info, sort_by, order)
        
        paginated_files = files_info[start:end]
        total_pages = math.ceil(len(files_info) / items_per_page)
        next_order = 'desc' if order == 'asc' else 'asc'

        self.render(
            "index.html",
            files=paginated_files,
            subpath=subpath,
            page=page,
            total_pages=total_pages,
            sort_by=sort_by,
            order=order,
            next_order=next_order
        )

class DownloadHandler(tornado.web.RequestHandler):
    def get(self, filepath):
        safe_path = os.path.join(self.application.settings['root_folder'], filepath)
        if not os.path.exists(safe_path):
            raise tornado.web.HTTPError(404)

        filename = os.path.basename(safe_path)
        mime_type, _ = mimetypes.guess_type(safe_path)
        if mime_type:
            self.set_header('Content-Type', mime_type)
        self.set_header('Content-Disposition', f'attachment; filename="{url_escape(filename)}"')
        
        with open(safe_path, 'rb') as file:
            self.write(file.read())

class UploadHandler(tornado.web.RequestHandler):
    def post(self, subpath=''):
        if 'file' not in self.request.files:
            self.redirect(f'/{subpath}')
            return

        file = self.request.files['file'][0]
        if not file.filename:
            self.redirect(f'/{subpath}')
            return

        filename = tornado.escape.xhtml_escape(file.filename)
        upload_folder = os.path.join(self.application.settings['root_folder'], subpath)
        
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        file_path = get_unique_filename(upload_folder, filename)
        with open(file_path, 'wb') as output_file:
            output_file.write(file.body)
        
        self.redirect(f'/{subpath}')

def get_unique_filename(upload_folder, filename):
    name, ext = os.path.splitext(filename)
    counter = 1
    file_path = os.path.join(upload_folder, filename)
    
    while os.path.exists(file_path):
        new_filename = f"{name}_{counter}{ext}"
        file_path = os.path.join(upload_folder, new_filename)
        counter += 1
    
    return file_path

def make_app(root_folder):
    return tornado.web.Application([
        (r"/upload/(.*)", UploadHandler),
        (r"/download/(.*)", DownloadHandler),
        (r"/(.*)", MainHandler),
    ], 
    template_path=os.path.join(os.path.dirname(__file__), "templates"),
    static_path=os.path.join(os.path.dirname(__file__), "static"),
    root_folder=root_folder,
    max_body_size=2 * 1024 * 1024 * 1024  # 2 GB limit
    )

def get_local_ip() -> str:
    try:
        # 创建一个 UDP socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # 连接到一个外部地址（不需要真实可达）
        s.connect(("8.8.8.8", 80))
        # 获取本地 IP
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        print(f"Error getting local IP: {e}")
        return "127.0.0.1"  # 如果失败，返回 localhost

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description="Simple File Browser Web Service")
    parser.add_argument("--root", type=str, default=os.getcwd(), help="The root folder to serve files from (default: current working directory)")
    parser.add_argument('--host', type=str, default='0.0.0.0', help="The host URL to bind to (default: 0.0.0.0)")
    parser.add_argument('--port', type=int, default=8080, help="The port to bind to (default: 8080)")
    args = parser.parse_args()

    print(f"Serving files from: {args.root}")
    app = make_app(args.root)

    if args.host == '0.0.0.0':
        print(f"Server is running on all local interfaces")
        local_ip = get_local_ip()
        print(f"Local IP: {local_ip}")
        print(f"Server is running on http://{local_ip}:{args.port} and http://127.0.0.1:{args.port}")
    else:
        print(f"Server is running on http://{args.host}:{args.port}")

    app.listen(args.port, args.host)
    tornado.ioloop.IOLoop.current().start()
