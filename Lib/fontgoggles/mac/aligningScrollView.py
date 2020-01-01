import AppKit
import vanilla
from ..misc.properties import hookedProperty


class AligningScrollView(vanilla.ScrollView):

    """ScrollView aligning its document view according to the `hAlign` and `vAlign`
    parameters.

    `hAlign` can be "left" (default), "center" or "right"
    `vAlign` can be "top" (default), "center" or "bottom"
    """

    def __init__(self, posSize, documentView, hAlign="left", vAlign="top",
                 drawBackground=True, minMagnification=None, maxMagnification=None,
                 borderType=AppKit.NSBezelBorder, clipview=None, **kwargs):
        self._docRef = [documentView]
        if hasattr(documentView, "_nsObject"):
            x, y, w, h = documentView._posSize
            assert x == 0 and y == 0, "posSize x and y must be 0 in document view"
            assert w >= 0 and h >= 0, "posSize w and h must be positive in document view"
            documentView = documentView._nsObject
            documentView.setFrame_(((0, 0), (w, h)))
        if clipview is None:
            clipView = _AligningScrollView_ClipView(hAlign, vAlign)
        super().__init__(posSize, documentView, clipView=clipView, **kwargs)
        clipView.setDrawsBackground_(drawBackground)  # Must be called _after_ super()
        scrollView = self._nsObject
        scrollView.setBorderType_(borderType)
        if maxMagnification is not None:
            scrollView.setAllowsMagnification_(True)
            scrollView.setMaxMagnification_(maxMagnification)
        if minMagnification is not None:
            scrollView.setAllowsMagnification_(True)
            scrollView.setMinMagnification_(minMagnification)

    @property
    def hAlign(self):
        return self._nsObject.contentView().hAlign

    @hAlign.setter
    def hAlign(self, value):
        self._nsObject.contentView().hAlign = value

    @property
    def vAlign(self):
        return self._nsObject.contentView().vAlign

    @vAlign.setter
    def vAlign(self, value):
        self._nsObject.contentView().vAlign = value


class _AligningScrollView_ClipView(AppKit.NSClipView):

    def __new__(cls, hAlign, vAlign):
        return cls.alloc().init()

    def __init__(self, hAlign, vAlign):
        self.hAlign = hAlign
        self.vAlign = vAlign
        self._prevClipBounds = self.bounds()
        self._prevDocBounds = None

    def mouseDown_(self, event):
        # A click occured in the clipview, but outside the document view. Happens when it is
        # smaller than the clipview. Make the document view first responder.
        docView = self.documentView()
        if docView.acceptsFirstResponder():
            self.window().makeFirstResponder_(docView)
            docView.mouseDown_(event)

    @hookedProperty
    def hAlign(self):
        self.setBounds_(self.constrainBoundsRect_(self.bounds()))

    @hookedProperty
    def vAlign(self):
        self.setBounds_(self.constrainBoundsRect_(self.bounds()))

    def viewFrameChanged_(self, notification):
        docBounds = self.documentView().bounds()
        if self._prevDocBounds is None:
            self._prevDocBounds = docBounds
            return

        widthDiff = docBounds.size.width - self._prevDocBounds.size.width
        heightDiff = docBounds.size.height - self._prevDocBounds.size.height

        # Given what we know about our alignment, try to keep the scroll
        # position "the same". So if we are right aligned and we grow,
        # grow to the left. If we are centered, grow left and right.
        clipBounds = self.bounds()
        if clipBounds.size.width < docBounds.size.width:
            if self.hAlign == "right":
                clipBounds.origin.x += widthDiff
            elif self.hAlign == "center":
                clipBounds.origin.x += widthDiff / 2
            self.setBounds_(clipBounds)
        # else: handled by self.constrainBoundsRect_()

        # Vertical
        if clipBounds.size.height < docBounds.size.height:
            if self.vAlign == "bottom":
                clipBounds.origin.y -= heightDiff
            elif self.vAlign == "center":
                clipBounds.origin.y -= heightDiff / 2
            self.setBounds_(clipBounds)

        self._prevDocBounds = docBounds
        super().viewFrameChanged_(notification)

    def constrainBoundsRect_(self, proposedClipBounds):
        # Partially taken from https://stackoverflow.com/questions/22072105/
        proposedClipBounds = super().constrainBoundsRect_(proposedClipBounds)
        docView = self.documentView()
        if docView is None:
            return proposedClipBounds
        docBounds = docView.bounds()
        scrollView = self.superview()
        magnification = scrollView.magnification()

        if self._prevClipBounds is not None:
            clipBounds = self.bounds()
            dx = clipBounds.origin.x - self._prevClipBounds.origin.x
            dy = clipBounds.origin.y - self._prevClipBounds.origin.y
            dw = clipBounds.size.width - self._prevClipBounds.size.width
            dh = clipBounds.size.height - self._prevClipBounds.size.height
        else:
            dx = dy = dw = dh = 0

        if proposedClipBounds.size.width > docBounds.size.width:
            if self.hAlign == "center":
                proposedClipBounds.origin.x = (docBounds.size.width - proposedClipBounds.size.width) / 2.0
            elif self.hAlign == "left":
                proposedClipBounds.origin.x = 0
            elif self.hAlign == "right":
                proposedClipBounds.origin.x = (docBounds.size.width - proposedClipBounds.size.width)
        else:
            if self.hAlign == "center":
                if dw != 0 or dx != 0:
                    proposedClipBounds.origin.x = self._prevClipBounds.origin.x - dw / 2 + dx
            elif self.hAlign == "right":
                maxX = docBounds.size.width - clipBounds.size.width
                if dw == 0 and dx == 0:
                    newX = proposedClipBounds.origin.x
                else:
                    newX = self._prevClipBounds.origin.x - dw + dx
                proposedClipBounds.origin.x = max(min(newX, maxX), -1)

        if proposedClipBounds.size.height > docBounds.size.height:
            if docView.isFlipped():
                # TODO: needs fixing for magnification
                if self.vAlign == "center":
                    proposedClipBounds.origin.y = (docBounds.size.height - proposedClipBounds.size.height) / 2.0
                elif self.vAlign == "top":
                    proposedClipBounds.origin.y = (docBounds.size.height - proposedClipBounds.size.height)
                elif self.vAlign == "bottom":
                    proposedClipBounds.origin.y = 0
            else:
                magBias = (magnification - 1) * proposedClipBounds.size.height
                if self.vAlign == "center":
                    proposedClipBounds.origin.y = -(docBounds.size.height - proposedClipBounds.size.height) / 2.0 + magBias
                elif self.vAlign == "top":
                    proposedClipBounds.origin.y = magBias
                elif self.vAlign == "bottom":
                    proposedClipBounds.origin.y = -(docBounds.size.height - proposedClipBounds.size.height) + magBias
        else:
            # TODO implement alignment for vertical
            pass

        self._prevClipBounds = proposedClipBounds
        return proposedClipBounds
