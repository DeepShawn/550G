import sys, math, random
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QAction, QPainter, QIcon, QColor, QFont
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon, QMessageBox

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/"assets"
LINES={"550G":["……嗯？","检测到摸鱼行为。","今天也要加油哦。","MOSS？不认识。","我只是在待机。"],"前辈GPT":["辛苦啦，休息一下吧。","今天也一起学习吧！","欸？你叫我吗？","不要把我放进冰箱哦。","保持理智，确实是一种奢求。"]}
PETS=[]

class Pet(QWidget):
    def __init__(self,name,svg,pos):
        super().__init__()
        self.name=name; self.svg=QSvgRenderer(str(ASSETS/svg)); self.resize(180,220)
        self.setWindowFlags(Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground,True)
        self.base=QPoint(*pos); self.drag=None; self.t=random.random()*6
        self.bubble=""; self.bubble_time=0; self.index=0; self.move(self.base)
        self.timer=QTimer(self); self.timer.timeout.connect(self.animate); self.timer.start(45)
    def animate(self):
        self.t+=.075
        if self.bubble_time>0:
            self.bubble_time-=1
            if self.bubble_time==0:self.bubble=""
        if self.drag is None:self.move(self.base.x(),self.base.y()+int(math.sin(self.t)*4))
        self.update()
    def say(self,msg=None):
        if msg is None:
            a=LINES[self.name]; msg=a[self.index%len(a)]; self.index+=1
        self.bubble=msg; self.bubble_time=85; self.update()
    def paintEvent(self,e):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self.bubble:
            p.setPen(QColor(180,194,210,220)); p.setBrush(QColor(255,255,255,240)); p.drawRoundedRect(3,3,174,39,12,12)
            p.setPen(QColor(55,70,85)); p.setFont(QFont("Microsoft YaHei UI",9)); p.drawText(9,8,162,29,Qt.AlignCenter|Qt.TextWordWrap,self.bubble)
        self.svg.render(p,self.rect().adjusted(0,40,0,0)); p.end()
    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton:self.drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft(); self.say()
        elif e.button()==Qt.RightButton:self.menu(e.globalPosition().toPoint())
    def mouseMoveEvent(self,e):
        if self.drag is not None and e.buttons()&Qt.LeftButton:
            self.base=e.globalPosition().toPoint()-self.drag; self.move(self.base)
    def mouseReleaseEvent(self,e):self.drag=None
    def menu(self,pos):
        m=QMenu(self); a=m.addAction(self.name); a.setEnabled(False); m.addSeparator()
        talk=m.addAction("说句话"); hide=m.addAction("隐藏这只"); hideall=m.addAction("隐藏全部"); m.addSeparator(); quit=m.addAction("退出桌宠")
        c=m.exec(pos)
        if c==talk:self.say()
        elif c==hide:self.hide()
        elif c==hideall:
            for p in PETS:p.hide()
        elif c==quit:QApplication.quit()

def main():
    app=QApplication(sys.argv); app.setApplicationName("550G × 前辈GPT 桌宠"); app.setQuitOnLastWindowClosed(False)
    g=app.primaryScreen().availableGeometry(); x=g.right()-390; y=g.bottom()-275
    PETS.extend([Pet("550G","550G.svg",(x,y)),Pet("前辈GPT","前辈GPT.svg",(x+195,y))])
    tray=QSystemTrayIcon(QIcon(str(ASSETS/"tray.svg")),app); tray.setToolTip("550G × 前辈GPT 桌宠")
    menu=QMenu(); show=menu.addAction("显示两只桌宠"); hide=menu.addAction("隐藏两只桌宠"); menu.addSeparator(); about=menu.addAction("关于"); quit=menu.addAction("退出")
    show.triggered.connect(lambda:[p.show() for p in PETS]); hide.triggered.connect(lambda:[p.hide() for p in PETS])
    about.triggered.connect(lambda:QMessageBox.information(None,"关于","550G × 前辈GPT 桌宠\\n第一版：双角色、拖动、对话气泡、托盘菜单。"))
    quit.triggered.connect(app.quit); tray.setContextMenu(menu); tray.activated.connect(lambda r:[p.show() for p in PETS] if r==QSystemTrayIcon.DoubleClick else None); tray.show()
    for p in PETS:p.show(); p.say("你好！我是"+p.name)
    sys.exit(app.exec())
if __name__=="__main__":main()
