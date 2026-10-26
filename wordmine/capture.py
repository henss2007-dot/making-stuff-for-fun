"""Screen grabbing and the drag-to-select region overlay."""

from __future__ import annotations

from typing import Optional

from PIL import Image

Region = dict  # {"left": int, "top": int, "width": int, "height": int}


def screen():
    """Open an mss screen-grabber (the class was renamed MSS in newer releases)."""
    import mss

    factory = getattr(mss, "MSS", None) or mss.mss
    return factory()


def grab(region: Optional[Region] = None) -> Image.Image:
    """Screenshot a region (or the whole virtual screen) as a PIL image."""
    with screen() as sct:
        shot = sct.grab(region or sct.monitors[0])
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def fingerprint(img: Image.Image) -> bytes:
    """Tiny grayscale thumbnail used to notice when the region's content changed."""
    return img.convert("L").resize((32, 16), Image.BILINEAR).tobytes()


def changed(a: Optional[bytes], b: Optional[bytes], threshold: float = 0.04) -> bool:
    """True when two fingerprints differ noticeably (or either is missing)."""
    if a is None or b is None or len(a) != len(b):
        return True
    diff = sum(abs(x - y) for x, y in zip(a, b)) / (len(b) * 255)
    return diff > threshold


class RegionSelector:
    """Full-screen translucent overlay; drag a rectangle, release to confirm.

    Escape cancels. Returns the region in screen coordinates or None.
    """

    def __init__(self, root):
        self.root = root
        self.result: Optional[Region] = None

    def select(self) -> Optional[Region]:
        import tkinter as tk

        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        # Cover the whole virtual desktop (all monitors) when we can measure it.
        try:
            with screen() as sct:
                vs = sct.monitors[0]
            top.geometry(f"{vs['width']}x{vs['height']}+{vs['left']}+{vs['top']}")
            ox, oy = vs["left"], vs["top"]
        except Exception:
            top.geometry(f"{top.winfo_screenwidth()}x{top.winfo_screenheight()}+0+0")
            ox, oy = 0, 0
        top.attributes("-topmost", True)
        try:
            top.attributes("-alpha", 0.3)
        except tk.TclError:
            pass
        top.configure(bg="black", cursor="crosshair")
        canvas = tk.Canvas(top, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            40, 30, anchor="nw", fill="white", font=("Segoe UI", 16),
            text="Drag over the game's text box.  Esc to cancel.",
        )
        state = {"x0": 0, "y0": 0, "rect": None}

        def press(e):
            state["x0"], state["y0"] = e.x, e.y
            state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#4af", width=2)

        def drag(e):
            if state["rect"] is not None:
                canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

        def release(e):
            x0, y0 = state["x0"], state["y0"]
            x1, y1 = e.x, e.y
            left, right = sorted((x0, x1))
            t, b = sorted((y0, y1))
            if right - left > 10 and b - t > 10:
                self.result = {"left": left + ox, "top": t + oy, "width": right - left, "height": b - t}
            top.destroy()

        def cancel(_e=None):
            self.result = None
            top.destroy()

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        top.bind("<Escape>", cancel)
        top.focus_force()
        top.grab_set()
        self.root.wait_window(top)
        return self.result


def monitor_for(region: Optional[Region]) -> Region:
    """The physical monitor containing the region's centre (whole desktop if none)."""
    with screen() as sct:
        monitors = sct.monitors
        if not region:
            return dict(monitors[0])
        cx = region["left"] + region["width"] // 2
        cy = region["top"] + region["height"] // 2
        for mon in monitors[1:]:
            if mon["left"] <= cx < mon["left"] + mon["width"] and mon["top"] <= cy < mon["top"] + mon["height"]:
                return dict(mon)
        return dict(monitors[0])


def grab_game_and_region(region: Optional[Region]) -> tuple[Image.Image, Image.Image]:
    """One screenshot of the game's monitor, plus the text-box crop out of it.

    Taking both from a single grab keeps the crop and the full screenshot in
    sync even while the game is animating.
    """
    mon = monitor_for(region)
    full = grab(mon)
    if not region:
        return full, full
    x = region["left"] - mon["left"]
    y = region["top"] - mon["top"]
    crop = full.crop((x, y, x + region["width"], y + region["height"]))
    return full, crop
