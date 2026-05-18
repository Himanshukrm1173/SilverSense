from PIL import Image, ImageDraw, ImageFont

def create_icon(size, filename):
    img = Image.new('RGB', (size, size), color='#0f0f0f')
    d = ImageDraw.Draw(img)
    # Draw a simple silver box in the middle
    box_size = size // 2
    x0 = (size - box_size) // 2
    y0 = (size - box_size) // 2
    d.rectangle([x0, y0, x0+box_size, y0+box_size], fill='#C0C0C0', outline='#E5E4E2', width=size//20)
    
    # Try to add "SS" text if possible
    try:
        font = ImageFont.load_default()
        d.text((size//2 - size//10, size//2 - size//10), "SS", fill="#0f0f0f", font=font)
    except:
        pass
        
    img.save(filename)

create_icon(192, 'static/icon-192.png')
create_icon(512, 'static/icon-512.png')
print("Icons generated.")
