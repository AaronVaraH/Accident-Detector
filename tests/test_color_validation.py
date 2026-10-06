import cv2
import numpy as np

# Simular recorte de manga en movimiento (gris/blanco, baja saturación)
blur_sleeve = np.full((100, 100, 3), (180, 175, 170), dtype=np.uint8)
hsv_sleeve = cv2.cvtColor(blur_sleeve, cv2.COLOR_BGR2HSV)
# Máscara de fuego en HSV: Hue entre 0 y 35 (rojos, naranjas, amarillos) y saturación > 100
mask_sleeve = cv2.inRange(hsv_sleeve, (0, 70, 150), (35, 255, 255))
fire_ratio_sleeve = np.sum(mask_sleeve > 0) / (100 * 100)

# Simular recorte de llama de encendedor (centro blanco/amarillo y borde naranja/rojo)
flame = np.zeros((100, 100, 3), dtype=np.uint8)
cv2.ellipse(flame, (50, 50), (20, 40), 0, 0, 360, (0, 200, 255), -1) # BGR naranja/amarillo
hsv_flame = cv2.cvtColor(flame, cv2.COLOR_BGR2HSV)
mask_flame = cv2.inRange(hsv_flame, (0, 70, 150), (35, 255, 255))
fire_ratio_flame = np.sum(mask_flame > 0) / (100 * 100)

print(f"Ratio color fuego en manga/blur: {fire_ratio_sleeve:.4f} (descartado)")
print(f"Ratio color fuego en llama: {fire_ratio_flame:.4f} (confirmado)")
