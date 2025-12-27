import sys
import asyncio
import qasync
from PySide6.QtWidgets import QApplication
from frontend.main_window import MainWindow
from backend.logger import logger

def main():
    logger.info("Initializing Application...")
    
    app = QApplication(sys.argv)
    
    # Integrate asyncio with Qt event loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    main_window = MainWindow(loop)
    main_window.show()
    
    logger.info("Application Ready.")
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
