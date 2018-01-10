#!/usr/bin/env python

"""osh5io.py: Disk IO for the OSIRIS HDF5 data."""

__author__ = "Han Wen"
__copyright__ = "Copyright 2018, PICKSC"
__credits__ = ["Adam Tableman", "Frank Tsung", "Thamine Dalichaouch"]
__license__ = "GPLv2"
__version__ = "0.1"
__maintainer__ = "Han Wen"
__email__ = "hanwen@ucla.edu"
__status__ = "Development"


import h5py
import os
import numpy as np
from osunit import OSUnits
from osaxis import DataAxis
from osh5def import H5Data, fn_rule


def read_h5(filename, path=None):
    """
    HDF reader for Osiris/Visxd compatible HDF files... This will slurp in the data
    and the attributes that describe the data (e.g. title, units, scale).

    Usage:
            diag_data = read_hdf('e1-000006.h5')      # diag_data is a subclass of numpy.ndarray with extra attributes

            print(diag_data)                          # print the meta data
            print(diag_data.view(numpy.ndarray))      # print the raw data
            print(diag_data.shape)                    # prints the dimension of the raw data
            print(diag_data.run_attrs['TIME'])        # prints the simulation time associated with the hdf5 file
            diag_data.data_attrs['UNITS']             # print units of the dataset points
            list(diag_data.data_attrs)                # lists all attributes related to the data array
            list(diag_data.run_attrs)                 # lists all attributes related to the run
            print(diag_data.axes[0].attrs['UNITS'])   # prints units of X-axis
            list(diag_data.axes[0].attrs)             # lists all variables of the X-axis

            diag_data[slice(3)]
                print(rw.view(np.ndarray))

    We will convert all byte strings stored in the h5 file to strings which are easier to deal with when writing codes
    see also write_h5() function in this file

    """
    fname = filename if not path else path + '/' + filename
    data_file = h5py.File(fname, 'r')

    the_data_hdf_object = scan_hdf5_file_for_main_data_array(data_file)

    timestamp, name, run_attrs, data_attrs, axes = '', '', {}, {}, []
    timestamp = fn_rule.findall(os.path.basename(filename))[0]
    name = the_data_hdf_object.name[1:]  # ignore the beginning '/'

    # now read in attributes of the ROOT of the hdf5..
    #   there's lots of good info there. strip out the array if value is a string
    for key, value in data_file.attrs.items():
        run_attrs[key] = value[0].decode('utf-8') if isinstance(value[0], bytes) else value

    # attach attributes assigned to the data array to
    #    the H5Data.data_attrs object, remove trivial dimension before assignment
    for key, value in the_data_hdf_object.attrs.items():
        data_attrs[key] = value[0].decode('utf-8') if isinstance(value[0], bytes) else value

    # convert unit string to osunit object
    try:
        data_attrs['UNITS'] = OSUnits(data_attrs['UNITS'])
    except KeyError:
        data_attrs['UNITS'] = OSUnits('')

    axis_number = 1
    while True:
        try:
            # try to open up another AXIS object in the HDF's attribute directory
            #  (they are named /AXIS/AXIS1, /AXIS/AXIS2, /AXIS/AXIS3 ...)
            axis_to_look_for = "/AXIS/AXIS" + str(axis_number)
            axis = data_file[axis_to_look_for]
            # convert byte string attributes to string
            attrs = {}
            for k, v in axis.attrs.items():
                attrs[k] = v[0].decode('utf-8') if isinstance(v[0], bytes) else v
            axis_min = axis[0]
            axis_max = axis[1]
            axis_numberpoints = the_data_hdf_object.shape[-axis_number]

            data_axis = DataAxis(axis_min, axis_max, axis_numberpoints, attrs=attrs)
            axes.insert(0, data_axis)
        except KeyError:
            break
        axis_number += 1

    # data_bundle.data = the_data_hdf_object[()]
    data_bundle = H5Data(the_data_hdf_object[()], timestamp=timestamp, name=name,
                         data_attrs=data_attrs, run_attrs=run_attrs, axes=axes)
    data_file.close()
    return data_bundle


def scan_hdf5_file_for_main_data_array(h5file):
    for k, v in h5file.items():
        if isinstance(v, h5py.Dataset):
            return h5file[k]
    else:
        raise Exception('Main data array not found')


def write_h5(data, filename=None, path=None, dataset_name=None, write_data=True):
    """
    Usage:
        write(diag_data, '/path/to/filename.h5')    # writes out Visxd compatible HDF5 data.

    Since h5 format does not support python strings, we will convert all string data (units, names etc)
    to bytes strings before writing.

    see also read_h5() function in this file

    """
    if isinstance(data, H5Data):
        data_object = data
    elif isinstance(data, np.ndarray):
        data_object = H5Data(data)
    else:
        try:  # maybe it's something we can wrap in a numpy array
            data_object = H5Data(np.array(data))
        except:
            raise Exception(
                "Invalid data type.. we need a 'hdf5_data', numpy array, or somehitng that can go in a numy array")

    # now let's make the H5Data() compatible with VisXd and such...
    # take care of the NAME attribute.
    if dataset_name is not None:
        current_name_attr = dataset_name
    elif data_object.name:
        current_name_attr = data_object.name
    else:
        current_name_attr = "Data"

    fname = path if path else ''
    if filename is not None:
        fname += filename
    elif data_object.timestamp is not None:
        fname += current_name_attr + '-' + data_object.timestamp + '.h5'
    else:
        raise Exception("You did not specify a filename!!!")
    if os.path.isfile(fname):
        os.remove(fname)
    h5file = h5py.File(fname)

    # now put the data in a group called this...
    h5dataset = h5file.create_dataset(current_name_attr, data_object.data.shape, data=data_object.data)
    # these are required.. so make defaults ones...
    h5dataset.attrs['UNITS'], h5dataset.attrs['LONG_NAME'] = np.array([b'']), np.array([b''])
    # convert osunit class back to ascii
    data_attrs = data_object.data_attrs.copy()
    try:
        data_attrs['UNITS'] = np.array([str(data_object.data_attrs['UNITS']).encode('utf-8')])
    except:
        data_attrs['UNITS'] = np.array([b'a.u.'])
    # copy over any values we have in the 'H5Data' object;
    for key, value in data_attrs.items():
        h5dataset.attrs[key] = np.array([value.encode('utf-8')]) if isinstance(value, str) else value
    # these are required so we make defaults..
    h5file.attrs['DT'] = [1.0]
    h5file.attrs['ITER'] = [0]
    h5file.attrs['MOVE C'] = [0]
    h5file.attrs['PERIODIC'] = [0]
    h5file.attrs['TIME'] = [0.0]
    h5file.attrs['TIME UNITS'] = [b'']
    h5file.attrs['TYPE'] = [b'grid']
    h5file.attrs['XMIN'] = [0.0]
    h5file.attrs['XMAX'] = [0.0]
    # now make defaults/copy over the attributes in the root of the hdf5
    for key, value in data_object.run_attrs.items():
        h5file.attrs[key] = np.array([value.encode('utf-8')]) if isinstance(value, str) else value

    number_axis_objects_we_need = len(data_object.axes)
    # now go through and set/create our axes HDF entries.
    for i in range(0, number_axis_objects_we_need):
        axis_name = "AXIS/AXIS%d" % (number_axis_objects_we_need - i)
        if axis_name not in h5file:
            axis_data = h5file.create_dataset(axis_name, (2,), 'float64')
        else:
            axis_data = h5file[axis_name]

        # set the extent to the data we have...
        axis_data[0] = data_object.axes[i].min()
        axis_data[1] = data_object.axes[i].max()

        # fill in any values we have stored in the Axis object
        for key, value in data_object.axes[i].attrs.items():
            axis_data.attrs[key] = value
    if write_data:
        h5file.close()


if __name__ == '__main__':
    a = np.arange(6.0).reshape(2, 3)
    ax, ay = DataAxis(0, 3, 3, attrs={'UNITS': '1 / \omega_p'}), DataAxis(10, 11, 2, attrs={'UNITS': 'c / \omega_p'})
    da = {'UNITS': OSUnits('n_0')}
    h5d = H5Data(a, timestamp='123456', name='test', data_attrs=da, axes=[ay, ax])
    write_h5(h5d, './test-123456.h5')
    rw = read_h5('./test-123456.h5')
    h5d = read_h5('./test-123456.h5')  # read from file to get all default attrs
    print("rw is h5d: ", rw is h5d, '\n')

    # let's read/write a few times and see if there are mutations to the data
    # you should also diff the output h5 files
    for i in range(5):
        write_h5(rw, './test' + str(i) + '-123456.h5')
        rw = read_h5('./test' + str(i) + '-123456.h5')
        assert (rw == a).all()
        for axrw, axh5d in zip(rw.axes, h5d.axes):
            assert axrw.attrs == axh5d.attrs
            assert (axrw == axh5d).all()
        assert h5d.timestamp == rw.timestamp
        assert h5d.name == rw.name
        assert h5d.data_attrs == rw.data_attrs
        assert h5d.run_attrs == rw.run_attrs
        print('checking: ', i+1, 'pass completed')

    # test some other functionaries
    print('\n meta info of rw: ', rw)
    print('\nunit of rw is ', rw.data_attrs['UNITS'])
    rw **= 3
    print('unit of rw^3 is ', rw.data_attrs['UNITS'])
    print('contents of rw^3: \n', rw.view(np.ndarray))


