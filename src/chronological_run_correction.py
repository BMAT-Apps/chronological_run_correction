#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 10 14:25:40 2021

@author: ColinVDB
Template
"""


import sys
import os
from os.path import join as pjoin
from os.path import exists as pexists
# from dicom2bids import *
import logging
from PyQt5.QtCore import (QSize,
                          Qt,
                          QModelIndex,
                          QMutex,
                          QObject,
                          QThread,
                          pyqtSignal,
                          QRunnable,
                          QThreadPool)
from PyQt5.QtWidgets import (QDesktopWidget,
                             QApplication,
                             QWidget,
                             QPushButton,
                             QMainWindow,
                             QLabel,
                             QLineEdit,
                             QVBoxLayout,
                             QHBoxLayout,
                             QFileDialog,
                             QDialog,
                             QTreeView,
                             QFileSystemModel,
                             QGridLayout,
                             QPlainTextEdit,
                             QMessageBox,
                             QListWidget,
                             QTableWidget,
                             QTableWidgetItem,
                             QMenu,
                             QAction,
                             QTabWidget,
                             QCheckBox)
from PyQt5.QtGui import (QFont,
                         QIcon)
import traceback
import threading
import subprocess
import pandas as pd
import platform
import json
import numpy as np
from bids_validator import BIDSValidator
import time


# from my_logging import setup_logging
from tqdm.auto import tqdm


def launch(parent, add_info=None):
    """
    

    Parameters
    ----------
    parent : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    """
    window = MainWindow(parent, add_info)
    window.show()



# =============================================================================
# MainWindow
# =============================================================================
class MainWindow(QMainWindow):
    """
    """
    

    def __init__(self, parent, add_info):
        """
        

        Parameters
        ----------
        parent : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        """
        super().__init__()
        self.parent = parent
        self.bids = self.parent.bids
        self.add_info = add_info

        self.setWindowTitle("Chronological Run Correction")
        self.window = QWidget(self)
        self.setCentralWidget(self.window)
        self.center()
        
        self.tab = ChronologicalRunCorrectionTab(self)
        layout = QVBoxLayout()
        layout.addWidget(self.tab)

        self.window.setLayout(layout)


    def center(self):
        """
        

        Returns
        -------
        None.

        """
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())



# =============================================================================
# TemplateTab
# =============================================================================
class ChronologicalRunCorrectionTab(QWidget):
    """
    """
    

    def __init__(self, parent):
        """
        

        Parameters
        ----------
        parent : TYPE
            DESCRIPTION.

        Returns
        -------
        None.

        """
        super().__init__()
        self.parent = parent
        self.bids = self.parent.bids
        self.add_info = self.parent.add_info
        self.setMinimumSize(500, 200)
        
        self.subjects_input = QLineEdit(self)
        self.subjects_input.setPlaceholderText("Select subjects")

        self.sessions_input = QLineEdit(self)
        self.sessions_input.setPlaceholderText("Select sessions")
        
        self.sequences_input = QLineEdit(self)
        self.sequences_input.setPlaceholderText("Select sequence to correct (optional)")

        self.run_chronological_corr_button = QPushButton("Run Chronological Correction")
        self.run_chronological_corr_button.clicked.connect(self.run_chronological_corr)

        layout = QVBoxLayout()
        layout.addWidget(self.subjects_input)
        layout.addWidget(self.sessions_input)
        layout.addWidget(self.sequences_input)
        layout.addWidget(self.run_chronological_corr_button)

        self.setLayout(layout)


    def run_chronological_corr(self):
        """
        

        Returns
        -------
        None.

        """
        subjects = self.subjects_input.text()
        sessions = self.sessions_input.text()
        sequences = self.sequences_input.text()
        self.subjects = []
        # find subjects
        if subjects == 'all':
            all_directories = [x for x in next(os.walk(self.bids.root_dir))[1]]
            for sub in all_directories:
                if sub.find('sub-') == 0:
                    self.subjects.append(sub.split('-')[1])
        else:
            subjects_split = subjects.split(',')
            for sub in subjects_split:
                if '-' in sub:
                    inf_bound = sub.split('-')[0]
                    sup_bound = sub.split('-')[1]
                    fill = len(inf_bound)
                    inf = int(inf_bound)
                    sup = int(sup_bound)
                    for i in range(inf,sup+1):
                        self.subjects.append(str(i).zfill(fill))
                else:
                    self.subjects.append(sub)

        # find sessions
        self.sessions = []
        if sessions == 'all':
            self.sessions.append('all')
        else:
            sessions_split = sessions.split(',')
            for ses in sessions_split:
                if '-' in ses:
                    inf_bound = ses.split('-')[0]
                    sup_bound = ses.split('-')[1]
                    fill = len(inf_bound)
                    inf = int(inf_bound)
                    sup = int(sup_bound)
                    for i in range(inf, sup+1):
                        self.sessions.append(str(i).zfill(fill))
                else:
                    self.sessions.append(ses)

        self.subjects_and_sessions = []
        for sub in self.subjects:
            if len(self.sessions) != 0:
                if self.sessions[0] == 'all':
                    all_directories = [x for x in next(os.walk(pjoin(self.bids.root_dir,f'sub-{sub}')))[1]]
                    sub_ses = []
                    for ses in all_directories:
                        if ses.find('ses-') == 0:
                            sub_ses.append(ses.split('-')[1])
                    self.subjects_and_sessions.append((sub,sub_ses))
                else:
                    self.subjects_and_sessions.append((sub,self.sessions))       
                    
        # Sequences input
        self.sequences = []
        if sequences == 'all' or sequences == '':
            self.sequences = 'all'
        else:
            self.sequences = sequences.split(',')
        
        self.thread = QThread()
        self.action = ChronologicalCorrectionWorker(self.bids, self.subjects_and_sessions, self.sequences)
        self.action.moveToThread(self.thread)
        self.thread.started.connect(self.action.run)
        self.action.in_progress.connect(self.is_in_progress)
        self.action.finished.connect(self.thread.quit)
        self.action.finished.connect(self.action.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()
        
        self.parent.hide()
        
        
    def is_in_progress(self, in_progress):
        self.parent.parent.work_in_progress.update_work_in_progress(in_progress)



# =============================================================================
# ActionWorker
# =============================================================================
class ChronologicalCorrectionWorker(QObject):
    """
    """
    finished = pyqtSignal()
    progress = pyqtSignal(int)
    in_progress = pyqtSignal(tuple)    
    

    def __init__(self, bids, subjects_and_sessions, sequences):
        """
        

        Returns
        -------
        None.

        """
        super().__init__()
        self.bids = bids
        self.subjects_and_sessions = subjects_and_sessions
        self.sequences = sequences
        

    def run(self):
        """
        

        Returns
        -------
        None.

        """
        # Action
        self.in_progress.emit(('Run Chronological Correction',True))
        
        print('Run Chronological Correction')
        
        for sub, sess, in self.subjects_and_sessions:
            for ses in sess:
                print(sub,ses)
                for root, dirs, files in os.walk(pjoin(self.bids.root_dir, f'sub-{sub}', f'ses-{ses}')):
                    if files == []:
                        continue
                    # for every sequences
                    if self.sequences == 'all':
                        # check all the different spaces of this particular subject
                        sequences = []
                        for file in files:
                            if '.nii.gz' in file:
                                seq = file.replace('.nii.gz', '')
                                space = seq.split('_')[-1]
                                if space not in sequences:
                                    sequences.append(space)
                        # self.sequences = sequences
                    else:
                        sequences = self.sequences
                    
                    nifti_files = [e for e in files if '.nii.gz' in e]
                    rest_files = [e for e in files if '.nii.gz' not in e]
                    
                    sequences_dic = {}
                    for seq in sequences:
                        # check all the repetition of this sequence for this subject with dates
                        # put everything in a dictionary
                        for file in nifti_files:
                            if seq in file:
                                file_no_ext = file.replace('.nii.gz', '')
                                seq_dic = {'name':file_no_ext}
                                # get time and ext
                                exts = []
                                for rfile in rest_files:
                                    if file_no_ext in rfile:
                                        if '.json' in rfile:
                                            with open(pjoin(root, rfile), 'r') as f:
                                                seq_info = json.load(f)
                                                mri_time = seq_info.get('AcquisitionTime')
                                                seq_dic['time'] = mri_time
                                        ext = rfile.split('.')[-1]
                                        exts.append(ext)
                                exts.append('nii.gz')
                                seq_dic['exts'] = exts
                                if sequences_dic.get(seq) == None:
                                    sequences_dic[seq] = [seq_dic]
                                else:
                                    sequences_dic[seq].append(seq_dic)
                                
                    # Check if it is well the same sequences apart from the run field
                    for key in sequences_dic.keys():
                        print(key)
                        seq_list = sequences_dic.get(key)
                        seq_list_details = [(e.get('name').split('_'),e.get('time'),e.get('exts')) for e in seq_list]
                        # remove run field if present
                        # seq_list_details_noRun = []
                        for i in range(len(seq_list_details)):
                            seq_list_details[i] = seq_list_details[i] + ([e for e in seq_list_details[i][0] if 'run' not in e],)
                            # seq_list_details_noRun.append(([e for e in seq_details[0] if 'run' not in e], seq_details[1], seq_details[2]))
                        
                        # check that every sequence has the same name
                        seq_list_name = [e[3] for e in seq_list_details]
                        seq_list_details_unique = np.unique(seq_list_name, axis=0)
                        
                    # Sort the sequences by a chronological order
                        for unseq in seq_list_details_unique:
                            if seq_list_name.count(list(unseq)) == 1:
                                continue
                            else:
                                unseq_list = [e for e in seq_list_details if e[3] == list(unseq)]
                                # sort unseq_list
                                unseq_list_sort = sorted(unseq_list, key=lambda x: pd.Timestamp(x[1]))
                                
                                # add the corresponding run chronological number
                                i = 1
                                for e in unseq_list_sort:
                                    if 'echo-' in e[3]:
                                        idx = ['echo-' in a for a in e[3]].index(True)
                                    elif 'part-' in e[3]:
                                        idx = ['part-' in a for a in e[3]].index(True)
                                    elif 'recording-' in e[3]:
                                        idx = ['recording-' in a for a in e[3]].index(True)
                                    else:
                                        idx = -1
                                    e[3].insert(idx, f'run-{i}')
                                    i = i+1
                                    
                                    for ext in e[2]:
                                        old_name = '_'.join(e[0])
                                        new_name = '_'.join(e[3])
                                        print(f'{old_name=}')
                                        print(f'{new_name=}')
                                        print(f'acq time = {e[1]}')
                                        os.rename(pjoin(root, f'{old_name}.{ext}'), pjoin(root, f'{new_name}.{ext}'))

        print('End of correction !')
        self.in_progress.emit(('Run Chronological Correction',False))
        self.finished.emit()


