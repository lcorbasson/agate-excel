#!/usr/bin/env python

"""
This module contains the XLS extension to :class:`Table <agate.table.Table>`.
"""

import datetime
from collections import OrderedDict

import agate
import six
import xlrd


EXCEL_TO_AGATE_TYPE = {
    xlrd.biffh.XL_CELL_EMPTY: agate.Boolean(),
    xlrd.biffh.XL_CELL_TEXT: agate.Text(),
    xlrd.biffh.XL_CELL_NUMBER: agate.Number(),
    xlrd.biffh.XL_CELL_DATE: agate.DateTime(),
    xlrd.biffh.XL_CELL_BOOLEAN: agate.Boolean(),
    xlrd.biffh.XL_CELL_ERROR: agate.Text(),
    xlrd.biffh.XL_CELL_BLANK: agate.Boolean(),
}


def from_xls(cls, path, sheet=None, skip_lines=0, header=True, encoding_override=None,
             row_limit=None, column_names=None, column_types=None, **kwargs):
    """
    Parse an XLS file.

    :param path:
        Path to an XLS file to load or a file-like object for one.
    :param sheet:
        The names or integer indices of the worksheets to load. If not specified
        then the first sheet will be used.
    :param skip_lines:
        The number of rows to skip from the top of the sheet.
    :param header:
        If :code:`True`, the first row is assumed to contain column names.
    :param row_limit:
        Limit how many rows of data will be read
    :param column_names:
        See :meth:`.Table.__init__`.
    :param column_types:
        See :meth:`.Table.__init__`.
    """
    if not isinstance(skip_lines, int):
        raise ValueError('skip_lines argument must be an int')

    if hasattr(path, 'read'):
        book = xlrd.open_workbook(file_contents=path.read(), encoding_override=encoding_override, on_demand=True)
    else:
        with open(path, 'rb') as f:
            book = xlrd.open_workbook(file_contents=f.read(), encoding_override=encoding_override, on_demand=True)

    try:
       multiple = agate.utils.issequence(sheet)
       if multiple:
           sheets = sheet
       else:
           sheets = [sheet]

       tables = OrderedDict()

       for i, sheet in enumerate(sheets):
           if isinstance(sheet, six.string_types):
               sheet = book.sheet_by_name(sheet)
           elif isinstance(sheet, int):
               sheet = book.sheet_by_index(sheet)
           else:
               sheet = book.sheet_by_index(0)

           if header:
               offset = 1
               column_names_detected = []
           else:
               offset = 0
               column_names_detected = None

           columns = []
           column_types_detected = []

           for i in range(sheet.ncols):
               if row_limit is None:
                   values = sheet.col_values(i, skip_lines + offset)
                   types = sheet.col_types(i, skip_lines + offset)
               else:
                   values = sheet.col_values(i, skip_lines + offset, skip_lines + offset + row_limit)
                   types = sheet.col_types(i, skip_lines + offset, skip_lines + offset + row_limit)
               excel_type = determine_excel_type(types)
               agate_type = determine_agate_type(excel_type)

               if excel_type == xlrd.biffh.XL_CELL_BOOLEAN:
                   values = normalize_booleans(values)
               elif excel_type == xlrd.biffh.XL_CELL_DATE:
                   values, with_date, with_time = normalize_dates(values, book.datemode)
                   if not with_date:
                       agate_type = agate.TimeDelta()
                   if not with_time:
                       agate_type = agate.Date()

               if header:
                   name = six.text_type(sheet.cell_value(skip_lines, i)) or None
                   column_names_detected.append(name)

               columns.append(values)
               column_types_detected.append(agate_type)

           rows = []

           if columns:
               for i in range(len(columns[0])):
                   rows.append([c[i] for c in columns])

           if column_names is None:
               sheet_column_names = column_names_detected
           else:
               sheet_column_names = column_names

           sheet_column_types = column_types
           if isinstance(column_types, dict) and sheet_column_names is not None:
               sheet_column_types = dict(zip(sheet_column_names, column_types_detected))
               sheet_column_types.update(column_types)

           tables[sheet.name] = agate.Table(rows, sheet_column_names, sheet_column_types, **kwargs)

    finally:
        book.release_resources()

    if multiple:
        return agate.MappedSequence(tables.values(), tables.keys())
    else:
        return tables.popitem()[1]


def determine_agate_type(excel_type):
    try:
        return EXCEL_TO_AGATE_TYPE[excel_type]
    except KeyError:
        return agate.Text()


def determine_excel_type(types):
    """
    Determine the correct type for a column from a list of cell types.
    """
    types_set = set(types)
    types_set.discard(xlrd.biffh.XL_CELL_EMPTY)

    # Normalize mixed types to text
    if len(types_set) > 1:
        return xlrd.biffh.XL_CELL_TEXT

    try:
        return types_set.pop()
    except KeyError:
        return xlrd.biffh.XL_CELL_EMPTY


def normalize_booleans(values):
    normalized = []

    for value in values:
        if value is None or value == '':
            normalized.append(None)
        else:
            normalized.append(bool(value))

    return normalized


def normalize_dates(values, datemode=0):
    """
    Normalize a column of date cells.
    """
    normalized = []
    with_date = False
    with_time = False

    for v in values:
        if not v:
            normalized.append(None)
            continue

        v_tuple = xlrd.xldate.xldate_as_datetime(v, datemode).timetuple()

        if v_tuple[3:6] == (0, 0, 0):
            # Date only
            normalized.append(datetime.date(*v_tuple[:3]))
            with_date = True
        elif v_tuple[:3] == (0, 0, 0):
            # Time only
            normalized.append(datetime.time(*v_tuple[3:6]))
            with_time = True
        else:
            # Date and time
            normalized.append(datetime.datetime(*v_tuple[:6]))
            with_date = True
            with_time = True

    return (normalized, with_date, with_time)


agate.Table.from_xls = classmethod(from_xls)
