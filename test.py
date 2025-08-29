import json

embedded_images = "https://www.google.com, https://www.baidu.com, https://www.facebook.com"

embedded_images_list = []
if embedded_images:
    try:
        if embedded_images.startswith('[') or embedded_images.startswith('{'):
            embedded_images_list = json.loads(embedded_images)
        else:
            embedded_images_list = [img.strip() for img in embedded_images.split(',') if img.strip()]
    except (json.JSONDecodeError, AttributeError):
        embedded_images_list = [embedded_images] if embedded_images else []

# Validate embedded_images structure
if embedded_images_list:
    for img in embedded_images_list:
        if not isinstance(img, str) or not img.startswith('http'):
            print({'error': 'Invalid embedded image format. Must be valid URLs'})

print(embedded_images_list)
print(len(embedded_images_list))
print(type(embedded_images_list))
for img in embedded_images_list:
    print(img)