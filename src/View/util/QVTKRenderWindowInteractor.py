import vtkmodules.qt
from vtkmodules.vtkRenderingCore import vtkRenderWindow
from vtkmodules.vtkRenderingUI import vtkGenericRenderWindowInteractor
from PySide6.QtWidgets import QWidget
from PySide6.QtWidgets import QSizePolicy
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtCore import QTimer
from PySide6.QtCore import QObject
from PySide6.QtCore import QSize
from PySide6.QtCore import QEvent

# Define types for base class, based on string
QVTKRWIBaseClass = QWidget


class QVTKRenderWindowInteractor(QVTKRWIBaseClass):
    _CURSOR_MAP = {
        0: Qt.ArrowCursor,  # VTK_CURSOR_DEFAULT
        1: Qt.ArrowCursor,  # VTK_CURSOR_ARROW
        2: Qt.SizeBDiagCursor,  # VTK_CURSOR_SIZENE
        3: Qt.SizeFDiagCursor,  # VTK_CURSOR_SIZENWSE
        4: Qt.SizeBDiagCursor,  # VTK_CURSOR_SIZESW
        5: Qt.SizeFDiagCursor,  # VTK_CURSOR_SIZESE
        6: Qt.SizeVerCursor,  # VTK_CURSOR_SIZENS
        7: Qt.SizeHorCursor,  # VTK_CURSOR_SIZEWE
        8: Qt.SizeAllCursor,  # VTK_CURSOR_SIZEALL
        9: Qt.PointingHandCursor,  # VTK_CURSOR_HAND
        10: Qt.CrossCursor,  # VTK_CURSOR_CROSSHAIR
    }

    def __init__(self, parent=None, **kw):
        # the current button
        self._ActiveButton = Qt.NoButton

        # private attributes
        self.__saveX = 0
        self.__saveY = 0
        self.__saveModifiers = Qt.NoModifier
        self.__saveButtons = Qt.NoButton
        self.__wheelDelta = 0

        # do special handling of some keywords:
        # stereo, rw

        try:
            stereo = bool(kw['stereo'])
        except KeyError:
            stereo = False

        try:
            rw = kw['rw']
        except KeyError:
            rw = None

        # create base qt-level widget

        if "wflags" in kw:
            wflags = kw['wflags']
        else:
            wflags = Qt.WindowFlags()
        QWidget.__init__(self, parent, wflags | Qt.MSWindowsOwnDC)

        if rw:  # user-supplied render window
            self._RenderWindow = rw
        else:
            self._RenderWindow = vtkRenderWindow()

        win_id = self.winId()

        # Python2
        if type(win_id).__name__ == 'PyCObject':
            from ctypes import pythonapi, c_void_p, py_object

            pythonapi.PyCObject_AsVoidPtr.restype = c_void_p
            pythonapi.PyCObject_AsVoidPtr.argtypes = [py_object]

            win_id = pythonapi.PyCObject_AsVoidPtr(win_id)

        # Python3
        elif type(win_id).__name__ == 'PyCapsule':
            from ctypes import pythonapi, c_void_p, py_object, c_char_p

            pythonapi.PyCapsule_GetName.restype = c_char_p
            pythonapi.PyCapsule_GetName.argtypes = [py_object]

            name = pythonapi.PyCapsule_GetName(win_id)

            pythonapi.PyCapsule_GetPointer.restype = c_void_p
            pythonapi.PyCapsule_GetPointer.argtypes = [py_object, c_char_p]

            win_id = pythonapi.PyCapsule_GetPointer(win_id, name)

        self._RenderWindow.SetWindowInfo(str(int(win_id)))

        if stereo:  # stereo mode
            self._RenderWindow.StereoCapableWindowOn()
            self._RenderWindow.SetStereoTypeToCrystalEyes()

        try:
            self._Iren = kw['iren']
        except KeyError:
            self._Iren = vtkGenericRenderWindowInteractor()
            self._Iren.SetRenderWindow(self._RenderWindow)

        # do all the necessary qt setup
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setAttribute(Qt.WA_PaintOnScreen)
        self.setMouseTracking(True)  # get all mouse events
        self.setFocusPolicy(Qt.WheelFocus)
        self.setSizePolicy(
            QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding))

        self._Timer = QTimer(self)
        self._Timer.timeout.connect(self.TimerEvent)

        self._Iren.AddObserver('CreateTimerEvent', self.CreateTimer)
        self._Iren.AddObserver('DestroyTimerEvent', self.DestroyTimer)
        self._Iren.GetRenderWindow().AddObserver('CursorChangedEvent',
                                                 self.CursorChangedEvent)

        # Create a hidden child widget and connect its destroyed signal to
        # its parent ``Finalize`` slot. The hidden children will be
        # destroyed before its parent thus allowing cleanup of VTK elements.
        self._hidden = QWidget(self)
        self._hidden.hide()
        self._hidden.destroyed.connect(self.Finalize)

    def __getattr__(self, attr):
        """Makes the object behave like a vtkGenericRenderWindowInteractor"""
        if attr == '__vtk__':
            return lambda t=self._Iren: t
        elif hasattr(self._Iren, attr):
            return getattr(self._Iren, attr)
        else:
            raise AttributeError(self.__class__.__name__ +
                                 " has no attribute named " + attr)

    def Finalize(self):
        """
        Call internal cleanup method on VTK objects
        """
        self._RenderWindow.Finalize()

    def CreateTimer(self, obj, evt):
        self._Timer.start(10)

    def DestroyTimer(self, obj, evt):
        self._Timer.stop()
        return 1

    def TimerEvent(self):
        self._Iren.TimerEvent()

    def CursorChangedEvent(self, obj, evt):
        """Called when the CursorChangedEvent fires on the render window."""
        # This indirection is needed since when the event fires, the current
        # cursor is not yet set so we defer this by which time the current
        # cursor should have been set.
        QTimer.singleShot(0, self.ShowCursor)

    def HideCursor(self):
        """Hides the cursor."""
        self.setCursor(Qt.BlankCursor)

    def ShowCursor(self):
        """Shows the cursor."""
        vtk_cursor = self._Iren.GetRenderWindow().GetCurrentCursor()
        qt_cursor = self._CURSOR_MAP.get(vtk_cursor, Qt.ArrowCursor)
        self.setCursor(qt_cursor)

    def closeEvent(self, evt):
        self.Finalize()

    def sizeHint(self):
        return QSize(400, 400)

    def paintEngine(self):
        return None

    def paintEvent(self, ev):
        self._Iren.Render()

    def resizeEvent(self, ev):
        scale = self._getPixelRatio()
        w = int(round(scale * self.width()))
        h = int(round(scale * self.height()))
        self._RenderWindow.SetDPI(int(round(72 * scale)))
        vtkRenderWindow.SetSize(self._RenderWindow, w, h)
        self._Iren.SetSize(w, h)
        self._Iren.ConfigureEvent()
        self.update()

    def _GetKeyCharAndKeySym(self, ev):
        """ Convert a Qt key into a char and a vtk keysym.

        This is essentially copied from the c++ implementation in
        GUISupport/Qt/QVTKInteractorAdapter.cxx.
        """
        # if there is a char, convert its ASCII code to a VTK keysym
        try:
            keyChar = ev.text()[0]
            keySym = _keysyms_for_ascii[ord(keyChar)]
        except IndexError:
            keyChar = '\0'
            keySym = None

        # next, try converting Qt key code to a VTK keysym
        if keySym is None:
            try:
                keySym = _keysyms[ev.key()]
            except KeyError:
                keySym = None

        # use "None" as a fallback
        if keySym is None:
            keySym = "None"

        return keyChar, keySym

    def _GetCtrlShift(self, ev):
        ctrl = shift = False

        if hasattr(ev, 'modifiers'):
            if ev.modifiers() & Qt.ShiftModifier:
                shift = True
            if ev.modifiers() & Qt.ControlModifier:
                ctrl = True
        else:
            if self.__saveModifiers & Qt.ShiftModifier:
                shift = True
            if self.__saveModifiers & Qt.ControlModifier:
                ctrl = True

        return ctrl, shift

    @staticmethod
    def _getPixelRatio():
        return 1.

    def _setEventInformation(self, x, y, ctrl, shift,
                             key, repeat=0, keysum=None):
        scale = self._getPixelRatio()
        self._Iren.SetEventInformation(int(round(x * scale)),
                                       int(round(
                                           (self.height() - y - 1) * scale)),
                                       ctrl, shift, key, repeat, keysum)

    def enterEvent(self, ev):
        ctrl, shift = self._GetCtrlShift(ev)
        self._setEventInformation(self.__saveX, self.__saveY,
                                  ctrl, shift, chr(0), 0, None)
        self._Iren.EnterEvent()

    def leaveEvent(self, ev):
        ctrl, shift = self._GetCtrlShift(ev)
        self._setEventInformation(self.__saveX, self.__saveY,
                                  ctrl, shift, chr(0), 0, None)
        self._Iren.LeaveEvent()

    def mousePressEvent(self, ev):
        ctrl, shift = self._GetCtrlShift(ev)
        repeat = 0
        if ev.type() == QEvent.MouseButtonDblClick:
            repeat = 1
        self._setEventInformation(ev.x(), ev.y(),
                                  ctrl, shift, chr(0), repeat, None)

        self._ActiveButton = ev.button()

        if self._ActiveButton == Qt.LeftButton:
            self._Iren.LeftButtonPressEvent()
        elif self._ActiveButton == Qt.RightButton:
            self._Iren.RightButtonPressEvent()
        elif self._ActiveButton == Qt.MiddleButton:
            self._Iren.MiddleButtonPressEvent()

    def mouseReleaseEvent(self, ev):
        ctrl, shift = self._GetCtrlShift(ev)
        self._setEventInformation(ev.x(), ev.y(),
                                  ctrl, shift, chr(0), 0, None)

        if self._ActiveButton == Qt.LeftButton:
            self._Iren.LeftButtonReleaseEvent()
        elif self._ActiveButton == Qt.RightButton:
            self._Iren.RightButtonReleaseEvent()
        elif self._ActiveButton == Qt.MiddleButton:
            self._Iren.MiddleButtonReleaseEvent()

    def mouseMoveEvent(self, ev):
        self.__saveModifiers = ev.modifiers()
        self.__saveButtons = ev.buttons()
        self.__saveX = ev.x()
        self.__saveY = ev.y()

        ctrl, shift = self._GetCtrlShift(ev)
        self._setEventInformation(ev.x(), ev.y(),
                                  ctrl, shift, chr(0), 0, None)
        self._Iren.MouseMoveEvent()

    def keyPressEvent(self, ev):
        key, keySym = self._GetKeyCharAndKeySym(ev)
        ctrl, shift = self._GetCtrlShift(ev)
        self._setEventInformation(self.__saveX, self.__saveY,
                                  ctrl, shift, key, 0, keySym)
        self._Iren.KeyPressEvent()
        self._Iren.CharEvent()

    def keyReleaseEvent(self, ev):
        key, keySym = self._GetKeyCharAndKeySym(ev)
        ctrl, shift = self._GetCtrlShift(ev)
        self._setEventInformation(self.__saveX, self.__saveY,
                                  ctrl, shift, key, 0, keySym)
        self._Iren.KeyReleaseEvent()

    def wheelEvent(self, ev):
        if hasattr(ev, 'delta'):
            self.__wheelDelta += ev.delta()
        else:
            self.__wheelDelta += ev.angleDelta().y()

        if self.__wheelDelta >= 120:
            self._Iren.MouseWheelForwardEvent()
            self.__wheelDelta = 0
        elif self.__wheelDelta <= -120:
            self._Iren.MouseWheelBackwardEvent()
            self.__wheelDelta = 0

    def GetRenderWindow(self):
        return self._RenderWindow

    def Render(self):
        self.update()


def QVTKRenderWidgetConeExample():
    """A simple example that uses the QVTKRenderWindowInteractor class."""

    from vtkmodules.vtkFiltersSources import vtkConeSource
    from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper, \
        vtkRenderer
    # load implementations for rendering and interaction factory classes
    import vtkmodules.vtkRenderingOpenGL2
    import vtkmodules.vtkInteractionStyle

    # every QT app needs an app
    app = QApplication(['QVTKRenderWindowInteractor'])

    # create the widget
    widget = QVTKRenderWindowInteractor()
    widget.Initialize()
    widget.Start()
    # if you don't want the 'q' key to exit comment this.
    widget.AddObserver("ExitEvent", lambda o, e, a=app: a.quit())

    ren = vtkRenderer()
    widget.GetRenderWindow().AddRenderer(ren)

    cone = vtkConeSource()
    cone.SetResolution(8)

    coneMapper = vtkPolyDataMapper()
    coneMapper.SetInputConnection(cone.GetOutputPort())

    coneActor = vtkActor()
    coneActor.SetMapper(coneMapper)

    ren.AddActor(coneActor)

    # show the widget
    widget.show()
    # start event processing
    app.exec_()


_keysyms_for_ascii = (
    None, None, None, None, None, None, None, None,
    None, "Tab", None, None, None, None, None, None,
    None, None, None, None, None, None, None, None,
    None, None, None, None, None, None, None, None,
    "space", "exclam", "quotedbl", "numbersign",
    "dollar", "percent", "ampersand", "quoteright",
    "parenleft", "parenright", "asterisk", "plus",
    "comma", "minus", "period", "slash",
    "0", "1", "2", "3", "4", "5", "6", "7",
    "8", "9", "colon", "semicolon", "less", "equal", "greater", "question",
    "at", "A", "B", "C", "D", "E", "F", "G",
    "H", "I", "J", "K", "L", "M", "N", "O",
    "P", "Q", "R", "S", "T", "U", "V", "W",
    "X", "Y", "Z", "bracketleft",
    "backslash", "bracketright", "asciicircum", "underscore",
    "quoteleft", "a", "b", "c", "d", "e", "f", "g",
    "h", "i", "j", "k", "l", "m", "n", "o",
    "p", "q", "r", "s", "t", "u", "v", "w",
    "x", "y", "z", "braceleft", "bar", "braceright", "asciitilde", "Delete",
)

_keysyms = {
    Qt.Key_Backspace: 'BackSpace',
    Qt.Key_Tab: 'Tab',
    Qt.Key_Backtab: 'Tab',
    # Qt.Key_Clear : 'Clear',
    Qt.Key_Return: 'Return',
    Qt.Key_Enter: 'Return',
    Qt.Key_Shift: 'Shift_L',
    Qt.Key_Control: 'Control_L',
    Qt.Key_Alt: 'Alt_L',
    Qt.Key_Pause: 'Pause',
    Qt.Key_CapsLock: 'Caps_Lock',
    Qt.Key_Escape: 'Escape',
    Qt.Key_Space: 'space',
    # Qt.Key_Prior : 'Prior',
    # Qt.Key_Next : 'Next',
    Qt.Key_End: 'End',
    Qt.Key_Home: 'Home',
    Qt.Key_Left: 'Left',
    Qt.Key_Up: 'Up',
    Qt.Key_Right: 'Right',
    Qt.Key_Down: 'Down',
    Qt.Key_SysReq: 'Snapshot',
    Qt.Key_Insert: 'Insert',
    Qt.Key_Delete: 'Delete',
    Qt.Key_Help: 'Help',
    Qt.Key_0: '0',
    Qt.Key_1: '1',
    Qt.Key_2: '2',
    Qt.Key_3: '3',
    Qt.Key_4: '4',
    Qt.Key_5: '5',
    Qt.Key_6: '6',
    Qt.Key_7: '7',
    Qt.Key_8: '8',
    Qt.Key_9: '9',
    Qt.Key_A: 'a',
    Qt.Key_B: 'b',
    Qt.Key_C: 'c',
    Qt.Key_D: 'd',
    Qt.Key_E: 'e',
    Qt.Key_F: 'f',
    Qt.Key_G: 'g',
    Qt.Key_H: 'h',
    Qt.Key_I: 'i',
    Qt.Key_J: 'j',
    Qt.Key_K: 'k',
    Qt.Key_L: 'l',
    Qt.Key_M: 'm',
    Qt.Key_N: 'n',
    Qt.Key_O: 'o',
    Qt.Key_P: 'p',
    Qt.Key_Q: 'q',
    Qt.Key_R: 'r',
    Qt.Key_S: 's',
    Qt.Key_T: 't',
    Qt.Key_U: 'u',
    Qt.Key_V: 'v',
    Qt.Key_W: 'w',
    Qt.Key_X: 'x',
    Qt.Key_Y: 'y',
    Qt.Key_Z: 'z',
    Qt.Key_Asterisk: 'asterisk',
    Qt.Key_Plus: 'plus',
    Qt.Key_Minus: 'minus',
    Qt.Key_Period: 'period',
    Qt.Key_Slash: 'slash',
    Qt.Key_F1: 'F1',
    Qt.Key_F2: 'F2',
    Qt.Key_F3: 'F3',
    Qt.Key_F4: 'F4',
    Qt.Key_F5: 'F5',
    Qt.Key_F6: 'F6',
    Qt.Key_F7: 'F7',
    Qt.Key_F8: 'F8',
    Qt.Key_F9: 'F9',
    Qt.Key_F10: 'F10',
    Qt.Key_F11: 'F11',
    Qt.Key_F12: 'F12',
    Qt.Key_F13: 'F13',
    Qt.Key_F14: 'F14',
    Qt.Key_F15: 'F15',
    Qt.Key_F16: 'F16',
    Qt.Key_F17: 'F17',
    Qt.Key_F18: 'F18',
    Qt.Key_F19: 'F19',
    Qt.Key_F20: 'F20',
    Qt.Key_F21: 'F21',
    Qt.Key_F22: 'F22',
    Qt.Key_F23: 'F23',
    Qt.Key_F24: 'F24',
    Qt.Key_NumLock: 'Num_Lock',
    Qt.Key_ScrollLock: 'Scroll_Lock',
}
