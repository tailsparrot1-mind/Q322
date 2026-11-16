import os
import sys
os.environ.setdefault('PYTHONUTF8', '1')
if sys.platform.startswith('linux'):
    os.environ.setdefault('WEBKIT_DISABLE_DMABUF_RENDERER', '1')
from vkus.exchange_visual import install_exchange_visuals
install_exchange_visuals()
from vkus.app import VkusApp
if __name__ == '__main__':
    VkusApp().run()
