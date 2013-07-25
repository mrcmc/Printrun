#!/usr/bin/env python

# This file is part of the Printrun suite.
#
# Printrun is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Printrun is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

from printrun.printrun_utils import install_locale, iconfile
install_locale('plater')

import os
import types
import wx

def patch_method(obj, method, replacement):
    orig_handler = getattr(obj, method)

    def wrapped(*a, **kwargs):
        kwargs['orig_handler'] = orig_handler
        return replacement(*a, **kwargs)
    setattr(obj, method, types.MethodType(wrapped, obj))

class Plater(wx.Frame):
    def __init__(self, filenames = [], size = (800, 580), callback = None, parent = None, build_dimensions = None):
        super(Plater, self).__init__(parent, title = _("Plate building tool"), size = size)
        self.filenames = filenames
        self.SetIcon(wx.Icon(iconfile("plater.ico"), wx.BITMAP_TYPE_ICO))
        self.mainsizer = wx.BoxSizer(wx.HORIZONTAL)
        panel = wx.Panel(self, -1)
        sizer = wx.GridBagSizer()
        self.l = wx.ListBox(panel)
        sizer.Add(self.l, pos = (1, 0), span = (1, 2), flag = wx.EXPAND)
        sizer.AddGrowableRow(1, 1)
        # Clear button
        clearbutton = wx.Button(panel, label = _("Clear"))
        clearbutton.Bind(wx.EVT_BUTTON, self.clear)
        sizer.Add(clearbutton, pos = (2, 0), span = (1, 2), flag = wx.EXPAND)
        # Load button
        loadbutton = wx.Button(panel, label = _("Load"))
        loadbutton.Bind(wx.EVT_BUTTON, self.load)
        sizer.Add(loadbutton, pos = (0, 0), span = (1, 1), flag = wx.EXPAND)
        # Snap to Z = 0 button
        snapbutton = wx.Button(panel, label = _("Snap to Z = 0"))
        snapbutton.Bind(wx.EVT_BUTTON, self.snap)
        sizer.Add(snapbutton, pos = (3, 0), span = (1, 1), flag = wx.EXPAND)
        # Put at center button
        centerbutton = wx.Button(panel, label = _("Put at center"))
        centerbutton.Bind(wx.EVT_BUTTON, self.center)
        sizer.Add(centerbutton, pos = (3, 1), span = (1, 1), flag = wx.EXPAND)
        # Delete button
        deletebutton = wx.Button(panel, label = _("Delete"))
        deletebutton.Bind(wx.EVT_BUTTON, self.delete)
        sizer.Add(deletebutton, pos = (4, 0), span = (1, 1), flag = wx.EXPAND)
        # Auto arrange button
        autobutton = wx.Button(panel, label = _("Auto arrange"))
        autobutton.Bind(wx.EVT_BUTTON, self.autoplate)
        sizer.Add(autobutton, pos = (5, 0), span = (1, 2), flag = wx.EXPAND)
        # Export button
        exportbutton = wx.Button(panel, label = _("Export"))
        exportbutton.Bind(wx.EVT_BUTTON, self.export)
        sizer.Add(exportbutton, pos = (0, 1), span = (1, 1), flag = wx.EXPAND)
        if callback is not None:
            donebutton = wx.Button(panel, label = _("Done"))
            donebutton.Bind(wx.EVT_BUTTON, lambda e: self.done(e, callback))
            sizer.Add(donebutton, pos = (6, 0), span = (1, 1), flag = wx.EXPAND)
            cancelbutton = wx.Button(panel, label = _("Cancel"))
            cancelbutton.Bind(wx.EVT_BUTTON, lambda e: self.Destroy())
            sizer.Add(cancelbutton, pos = (6, 1), span = (1, 1), flag = wx.EXPAND)
        self.basedir = "."
        self.models = {}
        panel.SetSizerAndFit(sizer)
        self.mainsizer.Add(panel, flag = wx.EXPAND)
        self.SetSizer(self.mainsizer)
        if build_dimensions:
            self.build_dimensions = build_dimensions
        else:
            self.build_dimensions = [200, 200, 100, 0, 0, 0]

    def set_viewer(self, viewer):
        # Patch handle_rotation on the fly
        if hasattr(viewer, "handle_rotation"):
            def handle_rotation(self, event, orig_handler):
                if self.initpos is None:
                    self.initpos = event.GetPositionTuple()
                else:
                    if not event.ShiftDown():
                        p1 = self.initpos
                        p2 = event.GetPositionTuple()
                        x1, y1, _ = self.mouse_to_3d(p1[0], p1[1])
                        x2, y2, _ = self.mouse_to_3d(p2[0], p2[1])
                        self.parent.move_shape((x2 - x1, y2 - y1))
                        self.initpos = p2
                    else:
                        orig_handler(event)
            patch_method(viewer, "handle_rotation", handle_rotation)
        # Patch handle_wheel on the fly
        if hasattr(viewer, "handle_wheel"):
            def handle_wheel(self, event, orig_handler):
                if not event.ShiftDown():
                    delta = event.GetWheelRotation()
                    angle = 10
                    if delta > 0:
                        self.parent.rotate_shape(angle / 2)
                    else:
                        self.parent.rotate_shape(-angle / 2)
                else:
                    orig_handler(event)
            patch_method(viewer, "handle_wheel", handle_wheel)
        self.s = viewer
        self.mainsizer.Add(self.s, 1, wx.EXPAND)

    def move_shape(self, delta):
        """moves shape (selected in l, which is list ListBox of shapes)
        by an offset specified in tuple delta.
        Positive numbers move to (rigt, down)"""
        name = self.l.GetSelection()
        if name == wx.NOT_FOUND:
            return False

        name = self.l.GetString(name)

        model = self.models[name]
        model.offsets = [model.offsets[0] + delta[0],
                         model.offsets[1] + delta[1],
                         model.offsets[2]
                         ]
        return True

    def rotate_shape(self, angle):
        """rotates acive shape
        positive angle is clockwise
        """
        name = self.l.GetSelection()
        if name == wx.NOT_FOUND:
            return False
        name = self.l.GetString(name)
        model = self.models[name]
        model.rot += angle

    def autoplate(self, event = None):
        print _("Autoplating")
        separation = 2
        bedsize = self.build_dimensions[0:3]
        cursor = [0, 0, 0]
        newrow = 0
        max = [0, 0]
        for i in self.models:
            self.models[i].offsets[2] = -1.0 * self.models[i].dims[4]
            x = abs(self.models[i].dims[0] - self.models[i].dims[1])
            y = abs(self.models[i].dims[2] - self.models[i].dims[3])
            centre = [x / 2, y / 2]
            centreoffset = [self.models[i].dims[0] + centre[0], self.models[i].dims[2] + centre[1]]
            if (cursor[0] + x + separation) >= bedsize[0]:
                cursor[0] = 0
                cursor[1] += newrow + separation
                newrow = 0
            if (newrow == 0) or (newrow < y):
                newrow = y
            #To the person who works out why the offsets are applied differently here:
            # Good job, it confused the hell out of me.
            self.models[i].offsets[0] = cursor[0] + centre[0] - centreoffset[0]
            self.models[i].offsets[1] = cursor[1] + centre[1] - centreoffset[1]
            if (max[0] == 0) or (max[0] < (cursor[0] + x)):
                max[0] = cursor[0] + x
            if (max[1] == 0) or (max[1] < (cursor[1] + x)):
                max[1] = cursor[1] + x
            cursor[0] += x + separation
            if (cursor[1] + y) >= bedsize[1]:
                print _("Bed full, sorry sir :(")
                self.Refresh()
                return
        centreoffset = [(bedsize[0] - max[0]) / 2, (bedsize[1] - max[1]) / 2]
        for i in self.models:
            self.models[i].offsets[0] += centreoffset[0]
            self.models[i].offsets[1] += centreoffset[1]
        self.Refresh()

    def clear(self, event):
        result = wx.MessageBox(_('Are you sure you want to clear the grid? All unsaved changes will be lost.'),
                               _('Clear the grid?'),
                               wx.YES_NO | wx.ICON_QUESTION)
        if result == 2:
            self.models = {}
            self.l.Clear()
            self.Refresh()

    def center(self, event):
        i = self.l.GetSelection()
        if i != -1:
            m = self.models[self.l.GetString(i)]
            m.offsets = [100, 100, m.offsets[2]]
            self.Refresh()

    def snap(self, event):
        i = self.l.GetSelection()
        if i != -1:
            m = self.models[self.l.GetString(i)]
            m.offsets[2] = -1.0 * min(m.facetsminz)[0]
            self.Refresh()

    def delete(self, event):
        i = self.l.GetSelection()
        if i != -1:
            del self.models[self.l.GetString(i)]
            self.l.Delete(i)
            self.l.Select(self.l.GetCount() - 1)
            self.Refresh()

    def add_model(self, name, model):
        newname = os.path.split(name.lower())[1]
        c = 1
        while newname in self.models:
            newname = os.path.split(name.lower())[1]
            newname = newname + "(%d)" % c
            c += 1
        self.models[newname] = model

        self.l.Append(newname)
        i = self.l.GetSelection()
        if i == wx.NOT_FOUND:
            self.l.Select(0)

        self.l.Select(self.l.GetCount() - 1)

    def load(self, event):
        dlg = wx.FileDialog(self, _("Pick file to load"), self.basedir, style = wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        dlg.SetWildcard(self.load_wildcard)
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetPath()
            self.load_file(name)
        dlg.Destroy()

    def load_file(self, filename):
        raise NotImplementedError

    def export(self, event):
        dlg = wx.FileDialog(self, _("Pick file to save to"), self.basedir, style = wx.FD_SAVE)
        dlg.SetWildcard(self.save_wildcard)
        if(dlg.ShowModal() == wx.ID_OK):
            name = dlg.GetPath()
            self.export_to(name)
        dlg.Destroy()

    def export_to(self, name):
        raise NotImplementedError