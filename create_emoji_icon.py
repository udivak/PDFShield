from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    # Create a transparent image
    size = (128, 128)
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw the emoji
    # Since loading system fonts with emojis can be tricky across OS, 
    # we'll draw a simple red circle with a white dash (No Entry sign) manually
    # to ensure it looks exactly like ⛔ and works without external font dependencies.
    
    # Draw Red Circle
    margin = 10
    draw.ellipse([margin, margin, size[0]-margin, size[1]-margin], fill='red')
    
    # Draw White Rectangle (The dash)
    rect_height = 20
    rect_width = 80
    rect_x = (size[0] - rect_width) / 2
    rect_y = (size[1] - rect_height) / 2
    draw.rectangle([rect_x, rect_y, rect_x + rect_width, rect_y + rect_height], fill='white')

    # Save
    output_path = 'extension/icon.png'
    img.save(output_path)
    print(f"Icon saved to {output_path}")

if __name__ == "__main__":
    create_icon()
