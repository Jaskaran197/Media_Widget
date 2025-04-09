import asyncio
import threading
import tkinter as tk
from PIL import Image, ImageTk, ImageDraw
from io import BytesIO
import winrt.windows.media.control as wmc
import winrt.windows.storage.streams as streams
import pystray
import ctypes
import sys
from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus

playback_status = "Unknown"

def load_icon(path, size=(40, 40)):
    img = Image.open(path).convert("RGBA").resize(size, Image.LANCZOS)
    return ImageTk.PhotoImage(img)


# ---------- Async Helper ----------
async def wait_winrt_async_operation(operation):
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    def callback(op, status):
        try:
            result = op.get_results()
            loop.call_soon_threadsafe(future.set_result, result)
        except Exception as e:
            loop.call_soon_threadsafe(future.set_exception, e)
    operation.completed = callback
    return await future

# ---------- Background Asyncio Loop ----------
loop = asyncio.new_event_loop()
def start_event_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()
threading.Thread(target=start_event_loop, daemon=True).start()

# ---------- Media Info ----------
async def get_media_info():
    sessions = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
    session = sessions.get_current_session()
    if not session:
        return None
    info = await session.try_get_media_properties_async()
    title = info.title
    artist = getattr(info, 'artist', 'Unknown') or "Unknown"
    stream = await info.thumbnail.open_read_async() if info.thumbnail else None

    image_data = None
    if stream:
        reader = streams.DataReader(stream)
        await wait_winrt_async_operation(reader.load_async(stream.size))
        image_data = bytes(reader.read_bytes(stream.size))

    return {
        "title": title,
        "artist": artist,
        "image_data": image_data,
        "controller": session
    }


async def update():
    media = await get_media_info()
    if not media:
        update_tray_icon("No media", "", None)
        label_title.config(text="No media playing")
        label_artist.config(text="")
        album_label.config(image='', text='')
        return

    label_title.config(text=media["title"])
    label_artist.config(text=media["artist"])

    if media["image_data"]:
        image = Image.open(BytesIO(media["image_data"])).resize((100, 100))
        photo = ImageTk.PhotoImage(image)

        album_label.config(image=photo)
        album_label.image = photo

    update_tray_icon(media["title"], media["artist"], media["image_data"])

    global media_session, playback_status
    media_session = media["controller"]
    status = media_session.get_playback_info().playback_status
    playback_status = status  # 4 = playing, 5 = paused

    if status == PlaybackStatus.PLAYING:
        play_pause_btn.config(image=pause_icon)
        play_pause_btn.image = pause_icon
    else:
        play_pause_btn.config(image=play_icon)
        play_pause_btn.image = play_icon

# ---------- Async Media Controls ----------
async def async_play_pause():
    if media_session:
        await media_session.try_toggle_play_pause_async()

async def async_skip_next():
    if media_session:
        await media_session.try_skip_next_async()

async def async_skip_previous():
    if media_session:
        await media_session.try_skip_previous_async()

# ---------- Tray Control Functions ----------
def tray_play_pause(icon, item):
    asyncio.run_coroutine_threadsafe(async_play_pause(), loop)

def tray_next(icon, item):
    asyncio.run_coroutine_threadsafe(async_skip_next(), loop)

def tray_prev(icon, item):
    asyncio.run_coroutine_threadsafe(async_skip_previous(), loop)

def toggle_widget(icon=None, item=None):
    global widget_visible
    if widget_visible:
        root.withdraw()
    else:
        root.deiconify()
    widget_visible = not widget_visible

def quit_app(icon=None, item=None):
    if icon:
        icon.stop()
    root.destroy()
    sys.exit()

# ---------- Tray Icon Setup ----------
def fallback_icon():
    img = Image.new("RGB", (64, 64), (34, 34, 34))
    draw = ImageDraw.Draw(img)
    draw.ellipse((16, 16, 48, 48), fill="white")
    return img

tray_icon = pystray.Icon("MediaWidget")
widget_visible = False

def run_tray():
    tray_icon.icon = fallback_icon()
    tray_icon.menu = pystray.Menu(
        pystray.MenuItem("Loading...", lambda: None, enabled=False),
        pystray.MenuItem("Show/Hide Widget", toggle_widget),
        pystray.MenuItem("Exit", quit_app)
    )
    tray_icon.run()

# ---------- Tray Info Refresh ----------
def update_tray_icon(title, artist, image_data):
    menu_items = [
        pystray.MenuItem(f"🎵 {title}", lambda: None, enabled=False),
        pystray.MenuItem(f"🎤 {artist}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("⏮ Previous", tray_prev),
        pystray.MenuItem("⏯ Play/Pause", tray_play_pause),
        pystray.MenuItem("⏭ Next", tray_next),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Show/Hide Widget", toggle_widget),
        pystray.MenuItem("Exit", quit_app)
    ]
    tray_icon.menu = pystray.Menu(*menu_items)

    if image_data:
        try:
            img = Image.open(BytesIO(image_data)).resize((64, 64))
            tray_icon.icon = img
        except:
            tray_icon.icon = fallback_icon()
    else:
        tray_icon.icon = fallback_icon()

# ---------- UI Update ----------
def update_ui():
    asyncio.run_coroutine_threadsafe(update(), loop)

# async def update():
#     media = await get_media_info()
#     if not media:
#         update_tray_icon("No media", "", None)
#         label_title.config(text="No media playing")
#         label_artist.config(text="")
#         album_label.config(image='', text='')
#         return

#     label_title.config(text=media["title"])
#     label_artist.config(text=media["artist"])

#     if media["image_data"]:
#         image = Image.open(BytesIO(media["image_data"])).resize((100, 100))
#         photo = ImageTk.PhotoImage(image)
#         album_label.config(image=photo)
#         album_label.image = photo

#     update_tray_icon(media["title"], media["artist"], media["image_data"])

#     global media_session
#     media_session = media["controller"]

# ---------- Tkinter Widget ----------
root = tk.Tk()
root.title("Now Playing")
root.geometry("180x240")
root.configure(bg="#222222")
root.attributes("-topmost", True)
root.attributes("-alpha", 0.95)
root.overrideredirect(True)

# Rounded corners (Windows 11)
try:
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWM_WINDOW_CORNER_PREFERENCE_ROUND = 2
    ctypes.windll.dwmapi.DwmSetWindowAttribute(
        hwnd,
        DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(ctypes.c_int(DWM_WINDOW_CORNER_PREFERENCE_ROUND)),
        ctypes.sizeof(ctypes.c_int())
    )
except Exception as e:
    print("Rounded corners not applied:", e)

# Draggable
def start_move(event):
    root.x = event.x
    root.y = event.y

def do_move(event):
    x = root.winfo_pointerx() - root.x
    y = root.winfo_pointery() - root.y
    root.geometry(f'+{x}+{y}')

root.bind('<Button-1>', start_move)
root.bind('<B1-Motion>', do_move)

label_title = tk.Label(
    root, text="Title", fg="white", bg="#222222",
    font=("Segoe UI", 12, "bold"),
    wraplength=160, justify="center"
)

label_artist = tk.Label(
    root, text="Artist", fg="lightgray", bg="#222222",
    font=("Segoe UI", 10),
    wraplength=160, justify="center"
)
album_label = tk.Label(root, bg="#222222")

button_frame = tk.Frame(root, bg="#222222")
btn_style = {
    "bg": "#444",
    "fg": "white",
    "font": ("Segoe UI", 10),
    "width": 3,
    "relief": "flat",
    "highlightthickness": 0,
    "bd": 0
}

prev_icon = load_icon("icons/prev.png")
play_icon = load_icon("icons/play.png")
pause_icon = load_icon("icons/pause.png")
next_icon = load_icon("icons/next.png")
icon_refs = [prev_icon, play_icon, pause_icon, next_icon]  # prevent garbage collection

tk.Button(button_frame, image=prev_icon, command=lambda: tray_prev(None, None),
          bg="#222222", bd=0, highlightthickness=0, activebackground="#222222").pack(side=tk.LEFT, padx=8)

play_pause_btn = tk.Button(button_frame, image=play_icon, command=lambda: tray_play_pause(None, None),
          bg="#222222", bd=0, highlightthickness=0, activebackground="#222222")
play_pause_btn.pack(side=tk.LEFT, padx=8)

tk.Button(button_frame, image=next_icon, command=lambda: tray_next(None, None),
          bg="#222222", bd=0, highlightthickness=0, activebackground="#222222").pack(side=tk.LEFT, padx=8)
def show_controls(event=None):
    label_title.pack(pady=(10, 0))
    label_artist.pack(pady=(0, 5))
    button_frame.pack(pady=5)


widgets = [root, album_label, label_title, label_artist, button_frame]
for widget in widgets:
    widget.bind('<Enter>', show_controls)


album_label.pack(pady=(10, 0))
show_controls()

# Refresh loop
def loop_update():
    update_ui()
    root.after(3000, loop_update)

media_session = None
update_ui()
loop_update()

# Start app
root.withdraw()
threading.Thread(target=run_tray, daemon=True).start()
tk.mainloop()
