import asyncio
import json
from os import PathLike
import os
import pathlib
import sys
from .font import getOpener


class Project:

    def __init__(self):
        self.fonts = []
        self.uiState = {}
        self.textState = {}
        self.fontSelection = set()  # not persistent
        self._fontLoader = FontLoader()
        self._fontItemIdentifierGenerator = self._fontItemIdentifierGeneratorFunc()

    @classmethod
    def fromJSON(cls, data, rootPath):
        return cls.fromDict(json.loads(data), rootPath)

    @classmethod
    def fromDict(cls, root, rootPath):
        self = cls()
        for fontItemInfoDict in root["fonts"]:
            fontPath = pathlib.Path(os.path.normpath(os.path.join(rootPath, fontItemInfoDict["path"])))
            self.addFont(fontPath, fontItemInfoDict["fontNumber"])
        self.uiState = root.get("uiState", {})
        self.textState = root.get("textState", {})
        return self

    def asJSON(self, rootPath):
        root = self.asDict(rootPath)
        return json.dumps(root, indent=2, ensure_ascii=False).encode("utf=8")

    def asDict(self, rootPath):
        root = {}
        root["fonts"] = []
        for fontItemInfo in self.fonts:
            fontPath, fontNumber = fontItemInfo.fontKey
            relFontPath = os.path.relpath(fontPath, rootPath)
            fontItemInfoDict = dict(path=relFontPath, fontNumber=fontNumber)
            root["fonts"].append(fontItemInfoDict)
        root["uiState"] = self.uiState
        root["textState"] = self.textState
        return root

    def addFont(self, path: PathLike, fontNumber: int, index=None):
        fontItemInfo = self.newFontItemInfo(path, fontNumber)
        if index is None:
            index = len(self.fonts)
        self.fonts.insert(index, fontItemInfo)

    def newFontItemInfo(self, path: PathLike, fontNumber: int):
        if not isinstance(path, PathLike):
            raise TypeError("path must be a Path(-like) object")
        if not isinstance(fontNumber, int):
            raise TypeError("fontNumber must be an integer")
        fontKey = (path, fontNumber)
        fontItemIdentifier = self._nextFontItemIdentifier()
        return FontItemInfo(fontItemIdentifier, fontKey, self._fontLoader)

    async def loadFonts(self, outputWriter=None):
        """Load fonts as concurrently as possible."""
        if outputWriter is None:
            outputWriter = sys.stderr.write
        await asyncio.gather(*(fontItemInfo.load(outputWriter)
                               for fontItemInfo in self.fonts if fontItemInfo.font is None))

    def _nextFontItemIdentifier(self):
        return next(self._fontItemIdentifierGenerator)

    @staticmethod
    def _fontItemIdentifierGeneratorFunc():
        counter = 0
        while True:
            yield f"fontItem_{counter}"
            counter += 1

    def purgeFonts(self):
        """Remove font objects that are no longer referenced in the fontItems
        list.
        """
        usedKeys = {fii.fontKey for fii in self.fonts}
        self._fontLoader.purgeFonts(usedKeys)


class FontItemInfo:

    def __init__(self, identifier, fontKey, fontLoader):
        self.identifier = identifier
        self.fontKey = fontKey
        self._fontLoader = fontLoader

    @property
    def fontPath(self):
        return self.fontKey[0]

    @fontPath.setter
    def fontPath(self, newFontPath):
        oldFontKey = self.fontKey
        fontNumber = oldFontKey[1]
        self.fontKey = newFontPath, fontNumber
        self._fontLoader.updateFontKey(oldFontKey, self.fontKey)
        font = self.font
        if font is not None:
            font.updateFontPath(newFontPath)

    @property
    def font(self):
        return self._fontLoader.fonts.get(self.fontKey)

    @property
    def wantsReload(self):
        return self.fontKey in self._fontLoader.wantsReload

    @wantsReload.setter
    def wantsReload(self, value):
        if value:
            self._fontLoader.wantsReload.add(self.fontKey)
        else:
            self._fontLoader.wantsReload.discard(self.fontKey)

    async def load(self, outputWriter=None):
        if outputWriter is None:
            outputWriter = sys.stderr.write
        await self._fontLoader.loadFont(self.fontKey, outputWriter)

    def unload(self):
        self._fontLoader.unloadFont(self.fontKey)


class FontLoader:

    def __init__(self):
        self.fonts = {}
        self.wantsReload = set()
        self.cachedFontData = {}

    def getData(self, fontPath):
        assert isinstance(fontPath, os.PathLike)
        fontData = self.cachedFontData.get(fontPath)
        if fontData is None:
            with open(fontPath, "rb") as f:
                fontData = f.read()
            self.cachedFontData[fontPath] = fontData
        return fontData

    async def loadFont(self, fontKey, outputWriter):
        font = self.fonts.get(fontKey)
        if font is not None:
            if fontKey in self.wantsReload:
                self.wantsReload.remove(fontKey)
                await font.load(outputWriter)
        else:
            path, fontNumber = fontKey
            numFonts, opener, getSortInfo = getOpener(path)
            assert fontNumber < numFonts(path)
            font = opener(path, fontNumber, self)
            await font.load(outputWriter)
            self.fonts[fontKey] = font

    def unloadFont(self, fontKey):
        self.fonts.pop(fontKey, None)  # discard
        self.cachedFontData = {}

    def purgeFonts(self, usedKeys):
        self.fonts = {fontKey: fontObject for fontKey, fontObject in self.fonts.items()
                      if fontKey in usedKeys}
        self.cachedFontData = {}

    def updateFontKey(self, oldFontKey, newFontKey):
        if oldFontKey not in self.fonts:
            # Font was not loaded, nothing to rename
            return
        self.fonts[newFontKey] = self.fonts.pop(oldFontKey)
