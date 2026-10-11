"""Generate a branded Windows ICO with Pillow at packaging time."""
from pathlib import Path
from PIL import Image, ImageDraw

def main():
    out = Path("build/assets")
    out.mkdir(parents=True, exist_ok=True)
    im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    pen = ImageDraw.Draw(im)
    pen.rounded_rectangle((5, 5, 250, 250), radius=57,
                          fill="#0A172A", outline="#E7C17F", width=11)
    pen.line([(65, 181), (65, 75), (185, 181), (185, 75)],
             fill="#E7C17F", width=23, joint="curve")
    pen.arc((11, 65, 73, 194), 100, 260, fill="#49DACC", width=9)
    pen.arc((183, 65, 244, 194), -80, 80, fill="#49DACC", width=9)
    im.save(out / "nexvary-voice.ico",
            sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    print("Created", out / "nexvary-voice.ico")

if __name__ == "__main__":
    main()
