import http.server
import socketserver
import socket
from urllib.parse import parse_qs

PORT = 8080
# Listen on all available network interfaces
HOST = '0.0.0.0'

class SimpleFormServer(http.server.BaseHTTPRequestHandler):
    """
    A simple HTTP request handler that serves a form and prints POST data.
    """

    def do_GET(self):
        """Handle GET requests by serving the HTML form."""
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Submit Text</title>
                <style>
                    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 1em; background-color: #f0f0f0; }
                    h1 { color: #333; }
                    form { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                    textarea { 
                        width: calc(100% - 22px); 
                        padding: 10px; 
                        font-size: 16px; 
                        border-radius: 4px; 
                        border: 1px solid #ccc;
                        min-height: 100px;
                    }
                    input[type="submit"] { 
                        display: block;
                        width: 100%;
                        padding: 12px 20px; 
                        font-size: 16px; 
                        margin-top: 10px; 
                        border: none;
                        border-radius: 4px;
                        background-color: #007bff;
                        color: white;
                        cursor: pointer;
                    }
                    input[type="submit"]:hover { background-color: #0056b3; }
                </style>
            </head>
            <body>
                <h1>Enter Text</h1>
                <p>Submit a link or any text below. It will appear in the terminal.</p>
                <form method="POST" action="/">
                    <textarea name="message" autofocus></textarea>
                    <br>
                    <input type="submit" value="Submit">
                </form>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode('utf-8'))
        else:
            self.send_error(404, f'File Not Found: {self.path}')

    def do_POST(self):
        """Handle POST requests by printing the form data."""
        try:
            content_length = int(self.headers['Content-Length'])
            post_data_bytes = self.rfile.read(content_length)
            post_data_str = post_data_bytes.decode('utf-8')
            params = parse_qs(post_data_str)

            if 'message' in params:
                message = params['message'][0]
                print("\\n" + "="*50)
                print("Received message:")
                print(message)
                print("="*50 + "\\n")


            # Redirect back to the form page after submission
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        except Exception as e:
            print(f"An error occurred during POST request: {e}")
            self.send_error(500, "Server error")

def get_local_ip():
    """
    Find the local IP address of the machine.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # This doesn't need to be a reachable address
        s.connect(('10.254.254.254', 1))
        ip_address = s.getsockname()[0]
    except Exception:
        ip_address = '127.0.0.1'
    finally:
        s.close()
    return ip_address

def run():
    """
    Starts the web server.
    """
    with socketserver.TCPServer((HOST, PORT), SimpleFormServer) as httpd:
        local_ip = get_local_ip()
        print("Server started.")
        print(f"Open this URL on your phone (ensure it's on the same Wi-Fi network):")
        print(f"--> http://{local_ip}:{PORT}")
        print("\\nPress Ctrl+C to stop the server.")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\\nServer is shutting down.")
            httpd.shutdown()

if __name__ == "__main__":
    run()
