#! /usr/bin/env python2.7

# xinput-ui
# A GUI front-end for the xinput utility, allowing graphical control over 
# X.Org's Multi-Pointer X (MPX) features. Created mainly as a project to learn 
# wxPython. The code is pretty horrible and has been cobbled together from 
# several tutorials.

# Copyright (c) 2013 Max Eliaser
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and/or associated documentation files (the
# "Materials"), to deal in the Materials without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Materials, and to
# permit persons to whom the Materials are furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Materials.
#
# THE MATERIALS ARE PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# MATERIALS OR THE USE OR OTHER DEALINGS IN THE MATERIALS.

# Sources I used:
#  - http://zetcode.com/wxpython/
#  - http://wiki.wxpython.org/

import wx, wx.gizmos
import subprocess
from string import whitespace as str_whitespace
import operator

INVALID_ID = -2
FLOATING_ID = -1

def run_command (command):
    p = subprocess.Popen(command,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    return iter(p.stdout.readline, b'')

# Strip all the extra Unicode characters "xinput list" likes to output
def mystrip (string):
    str_special = '\xe2\x8e\xa1\xe2\x8e\x9c\xe2\x86\xb3\xe2\x8e\xa3\x88\xbc'
    return string.strip(str_whitespace+str_special)

def device_sort (device_set):
    return sorted(device_set, key = operator.attrgetter ('self_id'))

# These device classes must all have a public "name" attribute

class MasterDevice: # virtual device
    
    def __init__ (self, name):
        self.name = name
        self.children = set()
        self.self_id = self.pointer_id = self.keyboard_id = INVALID_ID
    
    def set_pointer_id (self, pointer_id):
        self.pointer_id = pointer_id
        self.self_id = pointer_id # for device_sort
    
    def set_keyboard_id (self, keyboard_id):
        self.keyboard_id = keyboard_id
    
    def add_slave (self, slave_id, slave_name):
        assert self.self_id != INVALID_ID
        assert self.pointer_id != INVALID_ID
        assert self.keyboard_id != INVALID_ID
        self.children.add (SlaveDevice (self, slave_id, slave_name))

class SlaveDevice: # real physical hardware device
    
    def __init__ (self, parent, self_id, name):
        self.self_id = self_id
        self.name = name
        self.parent = parent
    
class PendingDevice: # virtual device which is pending creation
    
    def __init__ (self, name):
        self.name = name

# Reads the raw output of "xinput list" and parses it somewhat
def read_raw_device_data ():
    
    ret = {}
    
    for line in run_command (["/usr/bin/env", "xinput", "list"]):
        
        raw_device = [mystrip(field) for field in line.split ('\t')]
        raw_class_data = [field.strip('()') for field in raw_device[2][1:-1].split()]
        
        device_self_id = int (raw_device[1].split('=')[1])
        device_name = raw_device[0]
        
        # filter out XTEST devices
        if device_name.find ("XTEST") == -1:
            ret.update ({device_self_id: [device_name, raw_class_data]})
    
    return ret

# Returns a list of MasterDevice objects, each of which may be populated with
# SlaveDevice objects.
def get_device_status ():
    
    unsorted_devices = read_raw_device_data ()
    
    all_masters = {}
    # same as all_masters but with duplicate entries for keyboard device IDs.
    all_master_aliases = {} 
    
    # initialize master devices
    
    device = MasterDevice ("Unattached Devices")
    device.set_pointer_id (FLOATING_ID)
    device.set_keyboard_id (FLOATING_ID)
    all_master_aliases.update ({FLOATING_ID: device})
    all_masters.update ({FLOATING_ID: device})

    for device_id, rawdevice in unsorted_devices.iteritems():
        if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'pointer':
            continue
        device = MasterDevice (rawdevice[0])
        device.set_pointer_id (device_id)
        all_master_aliases.update ({device_id: device})
        all_masters.update ({device_id: device})
    
    for device_id, rawdevice in unsorted_devices.iteritems ():
        if rawdevice[1][0] != 'master' or rawdevice[1][1] != 'keyboard':
            continue
        device = all_master_aliases[int(rawdevice[1][2])]
        device.set_keyboard_id (device_id)
        all_master_aliases.update ({device_id: device})
    
    # initialize slave devices and attach them to their parent master devices
    
    for device_id, rawdevice in unsorted_devices.iteritems ():
        if rawdevice[1][0] == 'master':
            continue 
        master_id = None
        if rawdevice[1][0] == 'floating':
            master_id = FLOATING_ID
        else:
            master_id = int(rawdevice[1][2])
        all_master_aliases[master_id].add_slave (device_id, rawdevice[0])
    
    return all_masters

class DeviceTree (wx.gizmos.TreeListCtrl):
    
    def __init__ (self, window, panel):
        
        self.window = window
        
        label = wx.StaticBox (panel, label = "Devices:")
        sizer = wx.StaticBoxSizer (label, wx.VERTICAL)
        
        super (DeviceTree, self).__init__(panel, style = wx.TR_HIDE_ROOT | wx.TR_DEFAULT_STYLE | wx.SUNKEN_BORDER)
        
        self.AddColumn ("Name", 350)
        self.AddColumn ("ID", 30)
        self.root = self.AddRoot ("Pointers")
        sizer.Add(self, flag = wx.EXPAND, proportion = 1)
        
        panel.SetMinSize ((-1, 75))
        
        panel.SetSizer (sizer)
        
        self.Bind (wx.EVT_TREE_BEGIN_DRAG, self.OnBeginDrag)
        self.Bind (wx.EVT_TREE_END_DRAG, self.OnEndDrag)
        self.Bind (wx.EVT_TREE_ITEM_RIGHT_CLICK, self.OnRightClick)
        
        self.Bind (wx.EVT_TREE_SEL_CHANGED, self.OnSelectItem)
        
        self.all_devices = {}
        
        self.delete_callback = None
        self.selection_context = None
    
    def addMaster (self, device):
    
        menudev = self.AppendItem (self.root, device.name)
        self.SetItemPyData (menudev, device)
        
        for slave in device_sort(device.children):
            it = self.AppendItem (menudev, slave.name)
            self.SetItemText (it, str(slave.self_id), 1)
            self.SetItemPyData (it, slave) 
        
        self.Expand (menudev)
    
    def SetItemPyData (self, it, data):
        
        super (DeviceTree, self).SetItemPyData(it, data)
        
        self.all_devices.update ({data: it})
    
    def Delete (self, it, *args, **kwargs):
        
        # So "it" can be a menu item or a device object
        if it in self.all_devices:
            it = self.all_devices[it]
        
        super (DeviceTree, self).Delete (it, *args, **kwargs)
        
        data = self.GetItemPyData (it)
        if data != None:
            self.all_devices.pop (data)
    
    def DeleteAllItems (self, *args, **kwargs):
        
        super (DeviceTree, self).DeleteAllItems (*args, **kwargs)
        
        self.root = self.AddRoot ("Pointers")
        self.all_devices = {}
    
    def OnBeginDrag (self, evt):
        it = evt.GetItem ()
        self.dragItem = None
        if self.GetItemPyData(it).__class__ != SlaveDevice:
            return
        self.dragItem = it
        evt.Allow ()
    
    def FindListEntryParentDevice (self, listitem):
        if self.GetItemPyData(listitem).__class__ == SlaveDevice:
            listitem = self.GetItemParent (listitem)
        return self.GetItemPyData(listitem)
    
    def OnEndDrag (self, evt):
    
        if evt.GetItem ().IsOk ():
            target_menuitem = evt.GetItem ()
        else:
            return
        
        source_menuitem = self.dragItem
        
        if source_menuitem == None:
            return
        
        sourcemaster_device = self.FindListEntryParentDevice (source_menuitem)
        target_device = self.FindListEntryParentDevice (target_menuitem)
        source_device = self.GetItemPyData(source_menuitem)
        
        if sourcemaster_device == target_device:
            return
        
        self.window.cmdlist.MoveDeviceCmd (source_device, target_device)
    
    def OnSelectItem (self, evt):
        
        self.selection_context = None
        self.delete_callback = None
        self.window.toolbar.button_del.Enable (False)
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
        
        target_device = self.GetItemPyData(target)
        
        if target_device == None:
            self.selection_context = ctx_menu = wx.Menu ()
            self.window.cmdlist.MakeUndoMenuItem (ctx_menu, target_device)
            self.delete_callback = self.window.cmdlist.MakeDeleteMenuItem (ctx_menu, target_device)
            self.window.cmdlist.MakeMasterDeviceMenuItems (ctx_menu, target_device)
            
            if self.delete_callback != None:
                self.window.toolbar.button_del.Enable (True)
        
    def OnRightClick (self, evt):
        
        if evt.GetItem ().IsOk ():
            target = evt.GetItem ()
        else:
            return
        
        self.SelectItem (target)
        
        if self.selection_context != None:
            self.PopupMenu (self.selection_context)

# The main tooolbar.
class MainBar (wx.Panel):
    
    def __init__ (self, parent, panel):
        
        super (MainBar, self).__init__(panel)
        
        sizer = wx.BoxSizer (wx.HORIZONTAL)
        
        button_refresh = wx.Button (self, label='Refresh', id = wx.ID_REFRESH)
        sizer.Add (button_refresh)
        self.Bind (wx.EVT_BUTTON, parent.UI.refreshDevices, button_refresh)
        
        self.button_apply = wx.Button (self, label='Apply', id = wx.ID_APPLY)
        self.button_apply.Enable (False)
        sizer.Add (self.button_apply)
        self.Bind (wx.EVT_BUTTON, parent.cmdlist.Run, self.button_apply)
        
        button_new = wx.Button (self, label='Add', id = wx.ID_ADD)
        sizer.Add (button_new)
        self.Bind (wx.EVT_BUTTON, parent.OnNewMasterStart, button_new)
        
        self.button_del = wx.Button (self, label='Remove', id = wx.ID_REMOVE)
        self.button_del.Enable (False)
        sizer.Add (self.button_del)
        self.Bind (wx.EVT_BUTTON, parent.OnDelete, self.button_del)
        
        self.SetSizer (sizer)

# The toolbar that appears when you click on "Add." It has a text field for
# editing the name of the master pointer to create, as well as "OK" and 
# "Cancel" buttons.
class NewMasterBar (wx.Panel):
    
    def __init__ (self, parent, panel):
        
        self.parent = parent
        
        super (NewMasterBar, self).__init__(panel)
        
        sizer = wx.BoxSizer (wx.HORIZONTAL)
        
        label = wx.StaticText (self, label = "Name:")
        sizer.Add (label, flag = wx.ALIGN_CENTER)
        
        self.input = wx.TextCtrl (self, style = wx.TE_PROCESS_ENTER)
        sizer.Add (self.input, flag = wx.EXPAND, proportion = 1)
        self.Bind (wx.EVT_TEXT_ENTER, self.parent.OnNewMasterDone, self.input)
        
        button_confirm = wx.Button (self, label='OK', style = wx.BU_EXACTFIT, id = wx.ID_OK)
        sizer.Add (button_confirm, flag = wx.ALIGN_RIGHT)
        self.Bind (wx.EVT_BUTTON, self.parent.OnNewMasterDone, button_confirm)
        
        button_cancel = wx.Button (self, label='Cancel', style = wx.BU_EXACTFIT, id = wx.ID_CANCEL)
        sizer.Add (button_cancel, flag = wx.ALIGN_RIGHT)
        self.Bind (wx.EVT_BUTTON, self.OnCancel, button_cancel)
        
        self.SetSizer (sizer)
    
    def Show (self):
    
        self.parent.Show (self, True, True)
        
        self.input.SetValue ("New Pointer")
        self.input.SetSelection (0, -1)
        self.input.SetFocus()
        
        self.parent.Layout ()
    
    def Hide (self):
    
        self.parent.Show (self, False, True)
        self.parent.Layout ()
    
    def OnCancel (self, _):
        self.Hide ()
    
    def GetValue (self):
        return self.input.GetValue ()

# Used for tracking and displaying the "xinput" commands that will apply
# whatever changes are pending. You can think of this as tracking state
# changes. In other words, this is pretty much where the magic happens.
class CommandList (wx.ListCtrl):
    
    def __init__ (self, window, panel):
        
        self.window = window
        
        # used for categorizing different types of commands
        
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        
        # set up the GUI command list preview widget
        
        label = wx.StaticBox (panel, label = "Pending Commands:")
        sizer = wx.StaticBoxSizer (label, wx.VERTICAL)
        
        super (CommandList, self).__init__(panel, style = wx.LC_REPORT | wx.SUNKEN_BORDER | wx.LC_NO_HEADER)
        self.InsertColumn (0, "Commands", width = 250)
        sizer.Add (self, flag = wx.EXPAND, proportion = 1)
        
        panel.SetMinSize ((-1, 50))
        
        panel.SetSizer (sizer)
        
        # set up the list of commands we will actually execute
        
        # will be fed one at a time to run_command
        self.all_commands = [] 
    
    def AppendCommand (self, argslist):
        
        self.all_commands += [argslist]
        self.InsertStringItem (self.GetItemCount(), " ".join (argslist))
    
    def Regenerate (self):
        
        self.DeleteAllItems ()
        
        self.all_commands = []
        
        if len(self.all_moves) + len(self.all_deletions) + len(self.all_creations):
            self.window.toolbar.button_apply.Enable (True)
        else:
            self.window.toolbar.button_apply.Enable (False)
            return
        
        for source, dest in self.all_moves.iteritems():
            if dest.self_id == FLOATING_ID:
                # don't have to explicitly run a float command if the parent
                # is being deleted; that happens automatically
                if source.parent not in self.all_deletions:
                    self.AppendCommand (["xinput", "float", str(source.self_id)])
            else:
                self.AppendCommand (["xinput", "reattach", str(source.self_id), str(dest.pointer_id)])
                self.AppendCommand (["xinput", "reattach", str(source.self_id), str(dest.keyboard_id)])
        
        for device in self.all_deletions:
            self.AppendCommand (["xinput", "remove-master", str(device.self_id)])
        
        for device in self.all_creations:
            self.AppendCommand (["xinput", "create-master", device.name])
    
    def Run (self, evt):

        for cmd in self.all_commands:
            subprocess.Popen (["/usr/bin/env"] + cmd)

        # suppress the "unapplied pending changes" warning.
        self.all_commands = [] 

        self.window.UI.refreshDevices (evt)
    
    def MoveDeviceCmd (self, moved_device, target_device):
        
        if target_device in self.all_creations:
            wx.MessageBox (
                'Cannot add input devices to a pending pointer! '+
                'Hit "Apply" first to finish creating pointer "'+
                target_device.name+'"', 'Error', wx.OK | wx.ICON_EXCLAMATION
            )
            return
        
        if target_device in self.all_deletions:
            wx.MessageBox (
                'Pointer "'+target_device.name+'" is pending deletion! '+
                'To cancel deletion of this pointer, right-click it and '+
                'select "Cancel delete."', 'Error', wx.OK | wx.ICON_EXCLAMATION
            )
            return 
        
        target_menuitem = self.window.tree.all_devices[target_device]
        
        self.window.tree.Delete (moved_device)
        
        text = moved_device.name
        if moved_device.parent != target_device:
            text += ' (move pending)'
        
        new_menuitem = self.window.tree.AppendItem (target_menuitem, text)
        self.window.tree.SetItemText (new_menuitem, str(moved_device.self_id), 1)
        self.window.tree.SetItemPyData (new_menuitem, moved_device)
        self.window.tree.Expand (target_menuitem)
        
        if moved_device.parent == target_device:
            # a normal drag-and-drop operation has coincidentally had the same
            # effect as an undo operation
            self.all_moves.pop (moved_device, None)
        else:
            self.all_moves.update ({moved_device: target_device})
        
        self.Regenerate ()
    
    def DetachDeviceCmd (self, child_device):
        
        target_device = self.window.UI.master_devices[FLOATING_ID]
        self.MoveDeviceCmd (child_device, target_device)
    
    def UndoMoveDeviceCmd (self, device):
        
        self.MoveDeviceCmd (device, device.parent)
    
    def CreateDeviceCmd (self, new_device):
        
        self.all_creations.add (new_device)
        self.Regenerate ()
        
        menudev = self.window.tree.AppendItem (self.window.tree.root, new_device.name+' (pending)' )
        self.window.tree.SetItemPyData (menudev, new_device)
    
    def UndoCreateDeviceCmd (self, device):
        
        self.all_creations.remove (device)
        self.Regenerate ()
        
        self.window.tree.Delete (device)
    
    def DetachAllSlavesFromDeviceCmd (self, device):
        
        device_menuitem = self.window.tree.all_devices[device]
        
        while self.window.tree.ItemHasChildren (device_menuitem):
            child_menuitem, _ = self.window.tree.GetFirstChild(device_menuitem)
            child_device = self.window.tree.GetItemPyData(child_menuitem)
            self.DetachDeviceCmd (child_device)
    
    def ResetAllSlavesOfDeviceCmd (self, device):
        
        device_menuitem = self.window.tree.all_devices[device]
        
        # First undo any devices that have been moved to this master 
        
        # can't modify and iterate through the contents of the device tree 
        # simultaneously, so we need to defer our modifications
        children_to_move = set()
        
        nc = self.window.tree.GetChildrenCount(device_menuitem, 0)
        child_menuitem, cookie = self.window.tree.GetFirstChild(device_menuitem)
        for _ in xrange(nc):
            child_device = self.window.tree.GetItemPyData(child_menuitem)
            if child_device.parent != device:
                children_to_move.add (child_device)
            child_menuitem, cookie = self.window.tree.GetNextChild(device_menuitem, cookie)
        
        for child_device in children_to_move:
            self.UndoMoveDeviceCmd (child_device)
        
        # Now undo any devices that have been moved away from this master
        
        for child_device in device.children:
            self.UndoMoveDeviceCmd (child_device)
    
    def DeleteDeviceCmd (self, device):
        
        self.DetachAllSlavesFromDeviceCmd (device)
        self.all_deletions.add (device)
        self.window.tree.SetItemText (self.window.tree.all_devices[device], device.name + '(deleted)')
        self.Regenerate ()
    
    def UndoDeleteDeviceCmd (self, device):
        
        self.all_deletions.remove (device)
        self.window.tree.SetItemText (self.window.tree.all_devices[device], device.name)
        self.Regenerate ()
    
    def Reset (self):
        
        self.all_moves = {}
        self.all_deletions = set()
        self.all_creations = set()
        
        self.Regenerate ()
    
    #FIXME: this is kinda tedious
    
    def MakeUndoMenuItem (self, menu, device):
        
        item = None
        text = None
        action = None
        
        if device in self.all_deletions:
            text = 'Cancel delete '+device.name
            action = lambda _: self.UndoDeleteDeviceCmd (device)
        
        elif device in self.all_creations:
            text = 'Cancel create pointer '+device.name
            action = lambda _: self.UndoCreateDeviceCmd (device)
        
        elif device in self.all_moves and device.parent not in self.all_deletions:
            if self.all_moves[device].self_id == FLOATING_ID:
                text = 'Cancel detach '+device.name
            else:
                text = 'Cancel reattach '+device.name
            action = lambda _: self.UndoMoveDeviceCmd (device)
        
        else:
            return
        
        item = wx.MenuItem(menu, wx.NewId(), text)
        menu.AppendItem (item)
        menu.Bind(wx.EVT_MENU, action, item)
    
    def MakeDeleteMenuItem (self, menu, device):
        
        item = None
        text = None
        action = None
        
        if device in self.all_deletions or device in self.all_creations or device.self_id == FLOATING_ID:
            return None
        
        elif device in self.window.UI.master_devices.values():
            text = 'Delete '+device.name
            action = lambda _: self.DeleteDeviceCmd (device)
        
        elif device not in self.all_moves and device.parent.self_id == FLOATING_ID:
            return None
        
        elif device in self.all_moves and self.all_moves[device].self_id == FLOATING_ID:
            return None
        
        else:
            text = 'Detach '+device.name
            action = lambda _: self.DetachDeviceCmd (device)
        
        item = wx.MenuItem(menu, wx.NewId(), text)
        menu.AppendItem (item)
        menu.Bind(wx.EVT_MENU, action, item)
        
        return action
    
    def MakeMasterDeviceMenuItems (self, menu, device):
        
        if      device not in self.window.UI.master_devices.values() or \
                device in self.all_creations or \
                device in self.all_deletions or \
                device.self_id == FLOATING_ID:
            return
        
        reset_action = lambda _: self.ResetAllSlavesOfDeviceCmd (device)
        reset = wx.MenuItem (menu, wx.NewId(), 'Reset all devices for '+device.name)
        menu.AppendItem (reset)
        menu.Bind (wx.EVT_MENU, reset_action, reset)
        
        detach_all_action = lambda _: self.DetachAllSlavesFromDeviceCmd (device)
        detach_all = wx.MenuItem (menu, wx.NewId(), 'Detatch all devices from '+device.name)
        menu.AppendItem (detach_all)
        menu.Bind (wx.EVT_MENU, detach_all_action, detach_all)

class MainColumn (wx.BoxSizer):
    
    def __init__ (self, UI):
        
        self.UI = UI
        
        panel = wx.Panel (self.UI)
        
        super (MainColumn, self).__init__(wx.VERTICAL)
        
        splitter = wx.SplitterWindow (panel, -1)
        
        cmdpanel = wx.Panel (splitter)
        self.cmdlist = CommandList (self, cmdpanel)
        treepanel = wx.Panel (splitter)
        self.tree = DeviceTree (self, treepanel)
        
        splitter.SplitHorizontally (treepanel, cmdpanel)
        splitter.SetSashGravity (1.0)
        splitter.SetSashPosition (-100)
        
        self.toolbar = MainBar (self, panel)
        self.createmaster_toolbar = NewMasterBar (self, panel)
        
        self.Add (self.toolbar, flag = wx.ALIGN_TOP)
        self.Add (self.createmaster_toolbar, proportion = 0, flag = wx.ALIGN_TOP | wx.EXPAND)
        self.createmaster_toolbar.Hide ()
        self.Add (splitter, flag = wx.EXPAND, proportion = 1)
        
        panel.SetSizer (self)
        
    def clearTree (self):
        self.tree.DeleteAllItems ()
        self.cmdlist.Reset ()
    
    def OnDelete (self, evt):
        
        self.tree.delete_callback (evt)
    
    def OnNewMasterStart (self, _):
        
        self.createmaster_toolbar.Show ()
        
    def OnNewMasterDone (self, _):
        
        newdevice = PendingDevice (self.createmaster_toolbar.GetValue ())
        self.createmaster_toolbar.Hide ()
        
        self.cmdlist.CreateDeviceCmd (newdevice)

class UI (wx.Frame):
    
    def __init__(self, parent, title):
    
        super(UI, self).__init__(parent, title = title, size = (400, 500))
        
        self.SetMinSize ((340, 150))
        
        self.vbox = MainColumn (self)
        
        self.master_devices = get_device_status()
        
        self.initDevices ()
        
        self.Show ()
    
    def initDevices (self):
        
        for device in device_sort(self.master_devices.values()):
            if device.self_id != FLOATING_ID:
                self.vbox.tree.addMaster (device)
        
        # make sure the floating devices list comes last
        self.vbox.tree.addMaster (self.master_devices[FLOATING_ID])
    
    def refreshDevices (self, _):
        if len (self.vbox.cmdlist.all_commands):
            confirm = wx.MessageDialog (self,
                    'You still have pending changes! These will be lost if '+
                    'you refresh the device list. Refresh anyway?',
                    'Proceed?', wx.YES_NO | wx.ICON_QUESTION
                )
            result = confirm.ShowModal ()
            confirm.Destroy ()
            if result == wx.ID_NO:
                return
        self.master_devices = get_device_status()
        self.vbox.clearTree()
        self.initDevices ()

app = wx.App()
UI(None, title = 'Xinput-UI')
app.MainLoop()

 
