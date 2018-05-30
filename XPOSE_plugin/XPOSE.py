from ginga import GingaPlugin
from ginga.gw import Widgets

# import any other modules you want here--it's a python world!
import os
from datetime import datetime as dt
import numpy as np
from ginga import GingaPlugin, RGBImage, colors
from ginga.gw import Widgets
from ginga.misc import ParamSet, Bunch
from ginga.util import dp
from ginga.gw.GwHelp import FileSelection
from astropy.io import fits
from astropy.modeling import models, fitting
from scipy import ndimage
from socket import gethostname
from importlib import import_module
import Keck

class XPOSE(GingaPlugin.LocalPlugin):

    def __init__(self, fv, fitsimage):
        """
        This method is called when the plugin is loaded for the  first
        time.  ``fv`` is a reference to the Ginga (reference viewer) shell
        and ``fitsimage`` is a reference to the specific ImageViewCanvas
        object associated with the channel on which the plugin is being
        invoked.
        You need to call the superclass initializer and then do any local
        initialization.
        """
        super(XPOSE, self).__init__(fv, fitsimage)
        default_instrument = 'HIRES'
        # Determine instrument from hostname
        self.hostname = gethostname()
        hostnames = {'nuu': 'MOSFIRE',
                     'mosfireserver': 'MOSFIRE',
                     'vm-mosfire': 'MOSFIRE',
                     'mosfire': 'MOSFIRE',
                     'lehoula': 'HIRES',
                     'hiresserver': 'HIRES',
                     'vm-hires': 'HIRES',
                     'hires': 'HIRES',
                     'vm-esi': 'ESI',
                     'vm-nires': 'NIRES',
                     }
        try:
            instrument = hostnames[self.hostname]
            print(f'Hostname is "{self.hostname}"')
            print(f'Instrument is {instrument}')
        except KeyError:
            instrument = default_instrument
            print(f'Hostname "{self.hostname}" not matched to an instrument.')
            print(f'Assuming default instrument: {instrument}')

        print(f'Trying to instantiate {instrument}')
        try:
            INSTR_class = getattr(Keck, instrument)
            self.INSTR = INSTR_class()
            print(f'Got instance of {instrument}')
        except:
            print(f'Failed to instantiate {instrument}')

        print(f"Connected to {self.INSTR.name}")

        # Load plugin preferences
        prefs = self.fv.get_preferences()
        self.settings = prefs.createCategory('plugin_XPOSE')
        self.settings.setDefaults()
        self.settings.load(onError='silent')


        self.instructions = {
            True: 'For visible light instruments, you can configure the '\
              'OBJECT value, exposure time, and binning (if supported) using '\
              'the entry boxes below.  The "Take Test Exposure" button will '\
              'take a test exposure which is NOT saved.\n'\
              '\n'\
              'To take an observation sequence, choose a sequence type from '\
              'the pulldown menu and set the number of repeats in the box '\
              'below that (note: you must hit RETURN after entering a value). '\
              'Then click the "Start Observation Sequence" button.',
            False: 'For IR instruments, you can configure the OBJECT value, '\
              'exposure time, and number of coadds using the entry boxes '\
              'below.  To configure CDS readout, click "Set Bright Object".  '\
              'To configure MCDS16 readout click "Set Faint Object".  The '\
              '"Take Test Exposure" button will take a test exposure which '\
              'is NOT saved.\n'\
              '\n'\
              'To take an observation sequence, choose a sequence type from '\
              'the pulldown menu and set the number of repeats in the box '\
              'below that (note: you must hit RETURN after entering a value). '\
              'Then click the "Start Observation Sequence" button.',
               }


    def build_gui(self, container):
        """
        This method is called when the plugin is invoked.  It builds the
        GUI used by the plugin into the widget layout passed as
        ``container``.
        This method may be called many times as the plugin is opened and
        closed for modal operations.  The method may be omitted if there
        is no GUI for the plugin.

        This specific example uses the GUI widget set agnostic wrappers
        to build the GUI, but you can also just as easily use explicit
        toolkit calls here if you only want to support one widget set.
        """
        top = Widgets.VBox()
        top.set_border_width(4)

        # this is a little trick for making plugins that work either in
        # a vertical or horizontal orientation.  It returns a box container,
        # a scroll widget and an orientation ('vertical', 'horizontal')
        vbox, sw, orientation = Widgets.get_oriented_box(container)
        vbox.set_border_width(4)
        vbox.set_spacing(2)

        self.msg_font = self.fv.get_font("sansFont", 12)

        # Instructions
        tw_inst = Widgets.TextArea(wrap=True, editable=False)
        tw_inst.set_font(self.msg_font)
        self.tw_inst = tw_inst

        # Frame for instructions and add the text widget with another
        # blank widget to stretch as needed to fill emp
        fr_inst = Widgets.Expander("Instructions")
        fr_inst.set_widget(tw_inst)
        vbox.add_widget(fr_inst, stretch=0)


        ## -----------------------------------------------------
        ## Show Current Settings
        ## -----------------------------------------------------
        fr_show = Widgets.Frame(f"Current XPOSE Settings for {self.INSTR.name}")

        captions = [
                    ("Object:", "label",
                     "object", "llabel",
                     'set_object', 'entry'),
                    ("File Base Name:", "label",
                     "basename", "llabel"),
                    ("Frame No.:", "label",
                     "frameno", "llabel"),
                    ("Next File Name:", "label",
                     "filename", "llabel"),
                    ("ExpTime (s):", "label",
                     "itime", "llabel",
                     'set_itime', 'entry'),
                   ]
        if self.INSTR.optical is True:
            captions.extend([
                             ('Binning:', 'label',
                              'binning', 'llabel',
                              'set_binning', 'combobox'),
                             ('OBSTYPE:', 'label',
                              'obstype', 'llabel',
                              'set_obstype', 'combobox'),
                            ])
        else:
            captions.extend([
                             ("Coadds:", "label",
                              "coadds", "llabel",
                              'set_coadds', 'entry'),
                             ("Sampling Mode:", "label",
                              "sampmode", "llabel"),
                            ])

        w_show, b_show = Widgets.build_info(captions, orientation=orientation)
        self.w.update(b_show)

        b_show.object.set_text(f'{self.INSTR.object}')
        b_show.set_object.set_text(f'{self.INSTR.object}')
        b_show.set_object.add_callback('activated', self.cb_set_object)
        b_show.set_object.set_tooltip("Set object name for header")

        b_show.basename.set_text(f'{self.INSTR.basename}')
        b_show.frameno.set_text(f'{self.INSTR.frameno:d}')
        b_show.filename.set_text(f'{self.INSTR.get_filename()}')

        b_show.itime.set_text(f'{self.INSTR.itime:<.1f}')
        b_show.set_itime.set_text(f'{self.INSTR.itime:.2f}')
        b_show.set_itime.add_callback('activated', self.cb_set_itime)
        b_show.set_itime.set_tooltip("Set exposure time (s)")

        if self.INSTR.optical is True:
            b_show.binning.set_text(f'{self.INSTR.binning_as_str()}')
            combobox = b_show.set_binning
            for binopt in self.INSTR.binnings:
                combobox.append_text(binopt)
            b_show.set_binning.set_index(self.INSTR.binnings.index(self.INSTR.binning_as_str()))
            b_show.set_binning.add_callback('activated', self.cb_set_binning)

            b_show.obstype.set_text(f'{self.INSTR.get_obstype()}')
            combobox = b_show.set_obstype
            for type in self.INSTR.obstypes:
                combobox.append_text(type)
            b_show.set_obstype.set_index(self.INSTR.obstypes.index(self.INSTR.get_obstype()))
            b_show.set_obstype.add_callback('activated', self.cb_set_obstype)

        if self.INSTR.optical is False:
            b_show.coadds.set_text(f'{self.INSTR.coadds:d}')
            b_show.set_coadds.set_text(f'{self.INSTR.coadds:d}')
            b_show.set_coadds.add_callback('activated', self.cb_set_coadds)
            b_show.set_coadds.set_tooltip("Set number of Coadds")
            b_show.sampmode.set_text('{:d} ({})'.format(self.INSTR.sampmode,
                            self.INSTR.sampmode_trans[self.INSTR.sampmode]))

        fr_show.set_widget(w_show)
        vbox.add_widget(fr_show, stretch=0)


        ## -----------------------------------------------------
        ## Detector Parameter Controls

        if self.INSTR.optical is False:
            btns_params = Widgets.HBox()
            btns_params.set_spacing(1)

            btn_set_bright = Widgets.Button("Set Bright Object")
            btn_set_bright.add_callback('activated',
                                        lambda w: self.cb_set_bright(w))
            btns_params.add_widget(btn_set_bright, stretch=0)

            btn_set_faint = Widgets.Button("Set Faint Object")
            btn_set_faint.add_callback('activated',
                                       lambda w: self.cb_set_faint(w))
            btns_params.add_widget(btn_set_faint, stretch=0)

            vbox.add_widget(btns_params, stretch=0)


        ## -----------------------------------------------------
        ## Exposure Buttons

        btns_exp = Widgets.HBox()
        btns_exp.set_spacing(1)

        btn_start_exposure = Widgets.Button("Take Test Exposure")
        btn_start_exposure.add_callback('activated',
                                        lambda w: self.INSTR.start_exposure())
        btns_exp.add_widget(btn_start_exposure, stretch=0)

        if self.INSTR.optical is True:
            btn_abort_exposure = Widgets.Button("Abort Test Exposure")
            btn_abort_exposure.add_callback('activated',
                                            lambda w: self.INSTR.abort_exposure())
            btns_exp.add_widget(btn_abort_exposure, stretch=0)

        vbox.add_widget(btns_exp, stretch=0)



        ## -----------------------------------------------------
        ## Observation Sequence
        ## -----------------------------------------------------
        fr_sequence = Widgets.Frame("Observation Sequence")

        captions = (('Observation Sequence:', 'label',\
                     'sequence', 'llabel',\
                     'obsseq', 'combobox'),
                    ("Repeats:", 'label',\
                     'nrepeats', 'llabel',\
                     'set_repeats', 'entry',),
                    )
        w_script, b_script = Widgets.build_info(captions)
        self.w.update(b_script)

        combobox = b_script.obsseq
        for script in self.INSTR.scripts:
            combobox.append_text(script)
        b_script.obsseq.set_index(self.INSTR.scripts.index(self.INSTR.script))
        b_script.obsseq.add_callback('activated', self.cb_set_script)
        b_script.sequence.set_text(f'{self.INSTR.script}')

        b_script.nrepeats.set_text(f'{self.INSTR.repeats:d}')
        b_script.set_repeats.set_text(f'{self.INSTR.repeats:d}')
        b_script.set_repeats.add_callback('activated', self.cb_set_repeats)
        b_script.set_repeats.set_tooltip("Set number of repeats")

        fr_sequence.set_widget(w_script)
        vbox.add_widget(fr_sequence, stretch=0)

        ## -----------------------------------------------------
        ## Sequence Buttons

        btns_seq = Widgets.HBox()
        btns_seq.set_spacing(1)

        btn_start_sequence = Widgets.Button(f"Start Observation Sequence")
        btn_start_sequence.add_callback('activated',
                                        lambda w: self.INSTR.start_sequence())
        btns_seq.add_widget(btn_start_sequence, stretch=0)

        vbox.add_widget(btns_seq, stretch=0)

        btns_abortseq = Widgets.HBox()
        btns_abortseq.set_spacing(1)

        btn_abort_immediately = Widgets.Button("Abort Immediately")
        btn_abort_immediately.add_callback('activated',
                                           lambda w: self.INSTR.abort_immediately())
        btns_abortseq.add_widget(btn_abort_immediately, stretch=0)

        btn_abort_afterframe = Widgets.Button("Abort After Frame")
        btn_abort_afterframe.add_callback('activated',
                                          lambda w: self.INSTR.abort_afterframe())
        btns_abortseq.add_widget(btn_abort_afterframe, stretch=0)

#         btn_abort_afterrepeat = Widgets.Button("Abort After Repeat")
#         btn_abort_afterrepeat.add_callback('activated',
#                                            lambda w: self.INSTR.abort_afterrepeat())
#         btns_abortseq.add_widget(btn_abort_afterrepeat, stretch=0)


        vbox.add_widget(btns_abortseq, stretch=0)


        ## -----------------------------------------------------
        ## Instrument Specific Controls
        ## -----------------------------------------------------
        if self.INSTR.name == 'HIRES':
            ## HIRES Dewar
            fr_dwr = Widgets.Frame(f"HIRES Dewar")
            captions = [
                        ("Camera Dewar Level:", "label",
                         "dewar_level", "llabel",
                         "Fill Dewar", "button"),
                        ("Reserve Dewar Level:", "label",
                         "reserve_level", "llabel"),
                       ]
            w_dwr, b_dwr = Widgets.build_info(captions, orientation=orientation)
            self.w.update(b_dwr)

            b_dwr.dewar_level.set_text(f'{self.INSTR.get_DWRN2LV():5.1f}')
            b_dwr.reserve_level.set_text(f'{self.INSTR.get_RESN2LV():5.1f}')
            b_dwr.fill_dewar.add_callback('activated',
                                          lambda w: self.INSTR.fill_dewar())
            b_dwr.fill_dewar.set_tooltip(
                "Fill the camera dewar.  Takes roughly 15 minutes.")

            fr_dwr.set_widget(w_dwr)
            vbox.add_widget(fr_dwr, stretch=0)


            ## HIRES Exposure Meter
            fr_expo = Widgets.Frame(f"HIRES Exposure Meter")
            captions = [
                        ("System power:", "label",
                         "PMT0MPOW", "llabel",
                         "Toggle System Power", "button"),
                        ("System armed:", "label",
                         "is_armed", "llabel",
                         "Toggle Arming", "button"),
                        ("Exposure Set Point:", "label",
                         "setpoint", "llabel",
                         'set_setpoint', 'entry'),
                        ("Current Level:", "label",
                         "currentlevel", "llabel"),
                        ("Time Remaining (s):", "label",
                         "esttime", "llabel"),
                       ]
            w_expo, b_expo = Widgets.build_info(captions, orientation=orientation)
            self.w.update(b_expo)
            
#             b_expo.PMT0MPOW.set_text(f'{self.INSTR.expo_get_power_on()}')
#             b_expo.toggle_system_power.add_callback('activated',
#                                        lambda w: self.INST.expo_toggle_power())

            fr_expo.set_widget(w_expo)
            vbox.add_widget(fr_expo, stretch=0)

        ## -----------------------------------------------------
        ## Spacer
        ## -----------------------------------------------------

        # Add a spacer to stretch the rest of the way to the end of the
        # plugin space
        spacer = Widgets.Label('')
        vbox.add_widget(spacer, stretch=1)

        # scroll bars will allow lots of content to be accessed
        top.add_widget(sw, stretch=1)

        ## -----------------------------------------------------
        ## Bottom
        ## -----------------------------------------------------

        # A button box that is always visible at the bottom
        btns_close = Widgets.HBox()
        btns_close.set_spacing(3)

        # Add a close button for the convenience of the user
#         btn = Widgets.Button("Close")
#         btn.add_callback('activated', lambda w: self.close())
#         btns_close.add_widget(btn, stretch=0)

        btns_close.add_widget(Widgets.Label(''), stretch=1)
        top.add_widget(btns_close, stretch=0)

        # Add our GUI to the container
        container.add_widget(top, stretch=1)
        # NOTE: if you are building a GUI using a specific widget toolkit
        # (e.g. Qt) GUI calls, you need to extract the widget or layout
        # from the non-toolkit specific container wrapper and call on that
        # to pack your widget, e.g.:
        #cw = container.get_widget()
        #cw.addWidget(widget, stretch=1)


    def close(self):
        """
        Example close method.  You can use this method and attach it as a
        callback to a button that you place in your GUI to close the plugin
        as a convenience to the user.
        """
        self.fv.stop_local_plugin(self.chname, str(self))
        return True

    def start(self):
        """
        This method is called just after ``build_gui()`` when the plugin
        is invoked.  This method may be called many times as the plugin is
        opened and closed for modal operations.  This method may be omitted
        in many cases.
        """
        self.tw_inst.set_text(self.instructions[self.INSTR.optical])
        self.resume()

    def pause(self):
        """
        This method is called when the plugin loses focus.
        It should take any actions necessary to stop handling user
        interaction events that were initiated in ``start()`` or
        ``resume()``.
        This method may be called many times as the plugin is focused
        or defocused.  It may be omitted if there is no user event handling
        to disable.
        """
        pass

    def resume(self):
        """
        This method is called when the plugin gets focus.
        It should take any actions necessary to start handling user
        interaction events for the operations that it does.
        This method may be called many times as the plugin is focused or
        defocused.  The method may be omitted if there is no user event
        handling to enable.
        """
        pass

    def stop(self):
        """
        This method is called when the plugin is stopped.
        It should perform any special clean up necessary to terminate
        the operation.  The GUI will be destroyed by the plugin manager
        so there is no need for the stop method to do that.
        This method may be called many  times as the plugin is opened and
        closed for modal operations, and may be omitted if there is no
        special cleanup required when stopping.
        """
        pass

    def redo(self):
        """
        This method is called when the plugin is active and a new
        image is loaded into the associated channel.  It can optionally
        redo the current operation on the new image.  This method may be
        called many times as new images are loaded while the plugin is
        active.  This method may be omitted.
        """
        pass

    def __str__(self):
        """
        This method should be provided and should return the lower case
        name of the plugin.
        """
        return 'xpose'



    ## ------------------------------------------------------------------
    ##  Button Callbacks
    ## ------------------------------------------------------------------
    def cb_set_object(self, w):
        object = str(w.get_text())
        self.INSTR.set_object(object)
        self.w.object.set_text(f'{object}')


    def cb_set_itime(self, w):
        itime = float(w.get_text())
        self.INSTR.set_itime(itime)
        self.w.itime.set_text(f'{itime:.2f}')


    def cb_set_binning(self, w, index):
        self.INSTR.set_binning(self.INSTR.binnings[index])
        self.w.binning.set_text(self.INSTR.binning_as_str())


    def cb_set_obstype(self, w, index):
        self.INSTR.set_obstype(self.INSTR.obstypes[index])
        self.w.binning.set_text(f'{self.INSTR.get_obstype()}')


    def cb_set_coadds(self, w):
        coadds = int(w.get_text())
        self.INSTR.set_coadds(coadds)
        self.w.coadds.set_text(f'{self.INSTR.coadds:d}')


    def cb_set_bright(self, w):
        self.INSTR.set_bright()
        self.w.itime.set_text(f'{self.INSTR.itime:.2f}')
        self.w.set_itime.set_text(f'{self.INSTR.itime:.2f}')
        self.w.coadds.set_text(f'{self.INSTR.coadds:d}')
        self.w.set_coadds.set_text(f'{self.INSTR.coadds:d}')
        self.w.sampmode.set_text('{:d} ({})'.format(self.INSTR.sampmode,
                            self.INSTR.sampmode_trans[self.INSTR.sampmode]))


    def cb_set_faint(self, w):
        self.INSTR.set_faint()
        self.w.itime.set_text(f'{self.INSTR.itime:.2f}')
        self.w.set_itime.set_text(f'{self.INSTR.itime:.2f}')
        self.w.coadds.set_text(f'{self.INSTR.coadds:d}')
        self.w.set_coadds.set_text(f'{self.INSTR.coadds:d}')
        self.w.sampmode.set_text('{:d} ({})'.format(self.INSTR.sampmode,
                            self.INSTR.sampmode_trans[self.INSTR.sampmode]))


    def cb_set_repeats(self, w):
        nrepeats = int(w.get_text())
        self.INSTR.set_repeats(nrepeats)
        self.w.nrepeats.set_text(f'{self.INSTR.repeats:d}')


    def cb_set_script(self, w, index):
        self.INSTR.script = self.INSTR.scripts[index]
        self.w.sequence.set_text(f'{self.INSTR.script}')

