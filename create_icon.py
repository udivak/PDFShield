import base64
import os

# A simple 128x128 blue square PNG represented as base64
# Generated for fallback purposes
icon_base64 = "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAMAAAD04JH5AAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAADUExURlRk/605Z88AAAAJcEhZcwAADsMAAA7DAcdvqGQAAAA6SURBVHhe7cExAQAAAMKg9U9tDQ+gAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA4I0BQAAB1vD7CgAAAABJRU5ErkJggg=="

def create_icon():
    file_path = os.path.join('extension', 'icon.png')
    with open(file_path, "wb") as f:
        f.write(base64.b64decode(icon_base64))
    print(f"Created {file_path}")

if __name__ == "__main__":
    create_icon()
