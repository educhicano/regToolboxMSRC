# -*- coding: utf-8 -*-
"""
@author: pattenh1
"""

import os
import cv2
import SimpleITK as sitk
import ijroi
import numpy as np
import pandas as pd
import lxml.etree
import lxml.builder
import matplotlib
from matplotlib import cm


class ROIhandler(object):
    """Container class for handling ROIs loaded from ImageJ or a binary mask image.

    Parameters
    ----------
    roi_image_fp : str
        filepath to image that defines extents of box or a mask.
    img_res : float
        Pixel resolution of loaded image.
    is_mask : bool
        Whether the image filepath is a mask or only defines image extents

    """

    def __init__(self, roi_image_fp, img_res, is_mask=False):
        self.type = 'ROI Container'
        self.roi_image_fp = roi_image_fp
        target_image = sitk.ReadImage(roi_image_fp)
        self.img_res = float(img_res)

        self.zero_image = np.zeros(target_image.GetSize()[::-1])

        self.roi_corners = []

        if is_mask == True:
            self.roi_mask = sitk.ReadImage(roi_image_fp)
            self.roi_mask.SetSpacing((self.img_res, self.img_res))

    ##this function parses the ImageJ ROI file into all corners and far corners for rectangle ROIs
    #it only keeps the corners necessary for cv2 drawing
    def get_rectangles_ijroi(self, ij_rois_fp):
        """Short summary.

        Parameters
        ----------
        ij_rois_fp : str
            Filepath to an ImageJ ROI file

        Returns
        -------
        list
            Python lists of rectangle corners and all 4 corner coords.

        """

        rois = ijroi.read_roi_zip(ij_rois_fp)
        allcoords = [poly[1] for poly in rois]
        corners = [rect[[0, 2]] for rect in allcoords]
        self.roi_corners = corners
        self.allcoords = allcoords

    ###grabs polygonal ijrois
    def get_polygons_ijroi(self, ij_rois_fp):
        """Short summary.

        Parameters
        ----------
        ij_rois_fp : str
            Filepath to an ImageJ ROI file


        Returns
        -------
        list
            Python list of polygon verteces as numpy arrays

        """
        fn, fe = os.path.splitext(ij_rois_fp)
        print(fe)
        if fe == '.zip':
            rois = ijroi.read_roi_zip(ij_rois_fp)
        if fe == '.roi':
            rois = ijroi.read_roi(open(ij_rois_fp, "rb"))
        polyallcoords = [poly[1] for poly in rois]
        self.polygons = polyallcoords

    ##this function draws the mask needed for general FI rois
    def draw_rect_mask(self):
        """Draws uint8 binary mask image based on rectangle coords.

        Returns
        -------
        SimpleITK image
            Binary mask of loaded rect coords.

        """
        if len(self.roi_corners) == 0:
            raise ValueError('Rois have not been generated')

        for i in range(len(self.roi_corners)):
            if i == 0:
                filled = cv2.rectangle(
                    self.zero_image,
                    (self.roi_corners[i][0][1], self.roi_corners[i][0][0]),
                    (self.roi_corners[i][1][1], self.roi_corners[i][1][0]),
                    (255),
                    thickness=-1)
            else:
                filled = cv2.rectangle(
                    filled,
                    (self.roi_corners[i][0][1], self.roi_corners[i][0][0]),
                    (self.roi_corners[i][1][1], self.roi_corners[i][1][0]),
                    (255),
                    thickness=-1)
        self.box_mask = sitk.GetImageFromArray(filled.astype(np.int8))
        self.box_mask.SetSpacing((self.img_res, self.img_res))

    ##this function slices all the rois into sitk images
    def get_rect_rois_as_images(self, image_fp):
        """Slice images based on loaded rectangles.

        Parameters
        ----------
        image_fp : str
            Filepath to image to be sliced by rectangles

        Returns
        -------
        list
            Python list of SimpleITK images sliced by rectangles

        """
        if len(self.roi_corners) == 0:
            raise ValueError('Rois have not been generated')

        bg_image = sitk.ReadImage(image_fp)
        roi_slices = []

        for i in range(len(self.allcoords)):
            roi_slices.append(bg_image[self.allcoords[i][0][1]:self.allcoords[
                i][1][1], self.allcoords[i][0][0]:self.allcoords[i][3][0]])
        self.roi_slices = []
        self.roi_slices.append(roi_slices)

    def get_index_and_overlap(self,
                              ims_index_map_fp,
                              ims_res,
                              img_res,
                              use_key=False,
                              key_filepath=None):
        if self.polygons:
            ims_idx_np = sitk.GetArrayFromImage(
                sitk.ReadImage(ims_index_map_fp))
            scale_factor = ims_res / img_res
            zero_img = np.zeros(ims_idx_np.shape[::-1])

            for i in range(len(self.polygons)):
                fill = cv2.fillConvexPoly(zero_img, self.polygons[i].astype(
                    np.int32), i + 1)

            fill = np.transpose(fill)

            dfs = []

            for i in range(len(self.polygons)):
                whereresult = ims_idx_np[[
                    np.where(fill == i + 1)[0],
                    np.where(fill == i + 1)[1]
                ]]

                uniques, counts = np.unique(whereresult, return_counts=True)

                df_intermed = pd.DataFrame({
                    'roi_index':
                    i + 1,
                    'ims_index':
                    uniques,
                    'percentage':
                    counts / scale_factor**2
                })

                dfs.append(df_intermed)

            df = pd.concat(dfs)
            self.rois_ims_indexed = df
            if use_key == True and key_filepath != None:
                key = pd.read_csv(key_filepath, index_col=0)
                self.rois_ims_indexed['x_original'] = key.loc[np.searchsorted(
                    key.index.values, self.rois_ims_indexed['ims_index']
                    .values), ['x']].values

                self.rois_ims_indexed['y_original'] = key.loc[np.searchsorted(
                    key.index.values, self.rois_ims_indexed['ims_index']
                    .values), ['y']].values

                self.rois_ims_indexed['x_minimized'] = key.loc[np.searchsorted(
                    key.index.values, self.rois_ims_indexed['ims_index']
                    .values), ['x_minimized']].values

                self.rois_ims_indexed['y_minimized'] = key.loc[np.searchsorted(
                    key.index.values, self.rois_ims_indexed['ims_index']
                    .values), ['y_minimized']].values

        else:
            raise ValueError('polygon coordinates have not been loaded')

    def draw_polygon_mask(self, binary_mask=True, flip_xy=True):
        if self.polygons:
            zero_img = self.zero_image.copy()

            for i in range(len(self.polygons)):

                draw_polygons = self.polygons[i].astype(np.int32)
                if flip_xy == True:
                    draw_polygons[:, [0, 1]] = draw_polygons[:, [1, 0]]
                if binary_mask == True:
                    cc = cv2.fillConvexPoly(
                        zero_img, draw_polygons, 255, lineType=4)
                    self.pg_mask = sitk.GetImageFromArray(cc.astype(np.uint8))

                else:
                    cc = cv2.fillConvexPoly(
                        zero_img, draw_polygons, i + 1, lineType=4)
                    self.pg_mask = sitk.GetImageFromArray(cc.astype(np.uint32))

            #cc = np.transpose(cc)
            self.pg_mask.SetSpacing((self.img_res, self.img_res))

        else:
            raise ValueError('polygon coordinates have not been loaded')


def mask_contours_to_polygons(binary_mask, arcLenPercent=0.05):

    ret, threshsrc = cv2.threshold(binary_mask, 1, 256, 0)
    im2, contours, hierarchy = cv2.findContours(threshsrc, cv2.RETR_EXTERNAL,
                                                cv2.CHAIN_APPROX_NONE)

    approxPolygon = []

    for i in range(len(contours)):
        cnt = contours[i]
        epsilon = arcLenPercent * cv2.arcLength(cnt, True)
        polygon = cv2.approxPolyDP(cnt, epsilon, True)
        approxPolygon.append(polygon[:, 0, :])

    return (approxPolygon)


def mask_contours_to_boxes(binary_mask):

    ret, threshsrc = cv2.threshold(binary_mask, 1, 256, 0)
    im2, contours, hierarchy = cv2.findContours(threshsrc, cv2.RETR_EXTERNAL,
                                                cv2.CHAIN_APPROX_NONE)

    xs = []
    ys = []
    ws = []
    hs = []

    for i in range(len(contours)):
        cnt = contours[i]
        x, y, w, h = cv2.boundingRect(cnt)
        xs.append(x)
        ys.append(y)
        ws.append(w)
        hs.append(h)
    boxes = pd.DataFrame(xs, columns=['x1'])
    boxes['y1'] = ys
    boxes['x2'] = np.array(xs) + np.array(ws)
    boxes['y2'] = np.array(ys) + np.array(hs)

    boxes['p1'] = boxes['x1'].map(str) + ',' + boxes['y1'].map(str)
    boxes['p2'] = boxes['x2'].map(str) + ',' + boxes['y2'].map(str)

    boxes = boxes.sort_values(['y1'], ascending=True)
    boxes = boxes.reset_index()

    return (boxes)


#randomly split rois and reset parameters
def split_boxes(roi_coords,
                no_splits=4,
                base_name="base",
                ims_res="20",
                ims_method="par",
                roi_name="roi"):

    shuffled_rois = roi_coords.sample(frac=1)
    nrow_df = shuffled_rois.shape[0]
    no_per_group = nrow_df / no_splits
    select_seq = np.arange(0, nrow_df - 1, np.floor(no_per_group))

    splits = []
    for i in range(no_splits):

        if i == 0:
            splits.append(shuffled_rois.iloc[0:int(select_seq[i + 1])])

        elif i > 0 and i < no_splits - 1:

            first_idx = int(select_seq[i])
            last_idx = int(select_seq[i + 1])
            splits.append(shuffled_rois.iloc[first_idx:last_idx])

        else:

            first_idx = int(select_seq[i])
            last_idx = int(nrow_df)
            splits.append(shuffled_rois.iloc[first_idx:last_idx])

    for i in range(len(splits)):
        splits[i] = splits[i].sort_values(['y1'], ascending=True)
        splits[i] = splits[i].reset_index(drop=True)

        #save csv of data
        splits[i].to_csv(base_name + "_" + str(i) + ".csv", index=False)

        #parse csv file into flexImaging xml for RECTANGLES!!!! only!!
        output_flex_rects(
            splits[i],
            imsres=ims_res,
            imsmethod=ims_method,
            roiname=roi_name + "_split" + str(i) + "_",
            filename=base_name + "_" + str(i) + ".xml")


#randomly split rois and reset parameters
def split_polys(polygons,
                no_splits=4,
                base_name="base",
                ims_res="20",
                ims_method="par",
                roi_name="roi"):

    shuffled_rois = pd.Series(np.arange(0, len(polygons), 1)).sample(frac=1)
    shuffled_rois = shuffled_rois.tolist()
    polygons = np.array(polygons)[shuffled_rois].tolist()

    n_polygons = len(polygons)
    no_per_group = n_polygons / no_splits
    select_seq = np.arange(0, n_polygons - 1, np.floor(no_per_group))

    select_seq[1]
    i = 0
    splits = []
    for i in range(no_splits):

        if i == 0:
            splits.append(
                np.array(polygons)[0:int(select_seq[i + 1])].tolist())

        elif i > 0 and i < no_splits - 1:

            first_idx = int(select_seq[i])
            last_idx = int(select_seq[i + 1])
            splits.append(np.array(polygons)[first_idx:last_idx].tolist())

        else:

            first_idx = int(select_seq[i])
            last_idx = int(n_polygons)
            splits.append(np.array(polygons)[first_idx:last_idx].tolist())

    for i in range(len(splits)):
        #parse csv file into flexImaging xml for RECTANGLES!!!! only!!
        output_flex_polys(
            splits[i],
            imsres=ims_res,
            imsmethod=ims_method,
            roiname=roi_name + "_split" + str(i) + "_",
            filename=base_name + "_" + str(i) + ".xml")


def sort_pg_list(polygons):
    #fastest sorting for flexImaging import of polygons
    min_list = []
    for i in range(len(polygons)):
        min_list.append(np.min(polygons[i][:, 0]))

    polygons_sorted = np.array(polygons)[np.argsort(min_list)].tolist()

    ##doesn't work
    #for i in range(len(polygons_sorted)):
    #    polygons_sorted[i] = np.sort(polygons_sorted[i],axis=0)

    return polygons_sorted


##output xml file with FI compatible ROIs for polygons
def output_flex_polys(polygons,
                      imsres="100",
                      imsmethod="mymethod.par",
                      roiname="myroi_",
                      filename="myxml.xml",
                      idxed=False):

    #sort list from low to high y
    #this seems to produce less issues in flexImaging
    polygons = sort_pg_list(polygons)

    ##FI polygons to FlexImaging format:
    cmap = cm.get_cmap('Spectral', len(polygons))  # PiYG
    rgbs = []
    for i in range(cmap.N):
        rgb = cmap(
            i)[:3]  # will return rgba, we take only first 3 so we get rgb
        rgbs.append(matplotlib.colors.rgb2hex(rgb))

    polygon_df = pd.DataFrame(
        np.arange(1,
                  len(polygons) + 1, 1), columns=['idx'])
    polygon_df['namefrag'] = roiname
    polygon_df['name'] = polygon_df['namefrag'] + polygon_df['idx'].map(str)
    polygon_df['SpectrumColor'] = rgbs

    areaxmls = []

    for j in range(len(polygons)):
        if polygons[j].shape[0] > 1:
            E = lxml.builder.ElementMaker()
            ROOT = E.Area
            FIELD1 = E.Raster
            FIELD2 = E.Method
            POINTFIELDS = []

            for i in range(len(polygons[j])):
                POINTFIELDS.append(E.Point)

            imsraster = str(imsres) + ',' + str(imsres)

            if len(polygons[j]) < 3:
                output_type = 0
            else:
                output_type = 3
            the_doc = ROOT(
                '',
                Type=str(output_type),
                Name=polygon_df['name'][j],
                Enabled="0",
                ShowSpectra="0",
                SpectrumColor=polygon_df['SpectrumColor'][j])
            the_doc.append(FIELD1(imsraster))
            the_doc.append(FIELD2(imsmethod))
            for i in range(len(polygons[j])):
                the_doc.append(POINTFIELDS[i](
                    str(polygons[j][i][0]) + ',' + str(polygons[j][i][1])))

            areaxmls.append(
                lxml.etree.tostring(
                    the_doc, pretty_print=True, encoding='unicode'))
        else:
            pass
    f = open(filename, 'w')
    for i in range(len(areaxmls)):
        f.write(areaxmls[i])  # python will convert \n to os.linesep
    f.close()

    return


def output_flex_rects(boundingRect_df,
                      imsres="100",
                      imsmethod="mymethod.par",
                      roiname="myroi_",
                      filename="myxml.xml"):

    ##FI boxes to FlexImaging format:
    cmap = cm.get_cmap('Spectral', len(boundingRect_df))  # PiYG
    rgbs = []
    for i in range(cmap.N):
        rgb = cmap(
            i)[:3]  # will return rgba, we take only first 3 so we get rgb
        rgbs.append(matplotlib.colors.rgb2hex(rgb))

    metadata_df = pd.DataFrame(
        np.arange(1,
                  len(boundingRect_df) + 1, 1), columns=['idx'])
    metadata_df['namefrag'] = roiname
    metadata_df['name'] = metadata_df['namefrag'] + metadata_df['idx'].map(str)
    metadata_df['SpectrumColor'] = rgbs

    areaxmls = []

    for j in range(len(boundingRect_df)):
        E = lxml.builder.ElementMaker()
        ROOT = E.Area
        FIELD1 = E.Raster
        FIELD2 = E.Method
        POINT1 = E.Point
        POINT2 = E.Point

        imsraster = str(imsres) + ',' + str(imsres)

        the_doc = ROOT(
            '',
            Type="0",
            Name=metadata_df['name'][j],
            Enabled="0",
            ShowSpectra="0",
            SpectrumColor=metadata_df['SpectrumColor'][j])
        the_doc.append(FIELD1(imsraster))
        the_doc.append(FIELD2(imsmethod))
        the_doc.append(POINT1(str(boundingRect_df['p1'][j])))
        the_doc.append(POINT2(str(boundingRect_df['p2'][j])))

        areaxmls.append(
            lxml.etree.tostring(
                the_doc, pretty_print=True, encoding='unicode'))

    f = open(filename, 'w')
    for i in range(len(areaxmls)):
        f.write(areaxmls[i])  # python will convert \n to os.linesep
    f.close()


# def bruker_output_xmls(source_fp,
#                        target_fp,
#                        wd,
#                        ijroi_fp,
#                        project_name,
#                        ims_resolution=10,
#                        ims_method="par",
#                        roi_name="roi",
#                        splits="0"):
#
#     ts = datetime.datetime.fromtimestamp(
#         time.time()).strftime('%Y%m%d_%H_%M_%S_')
#     no_splits = int(splits)
#
#     #register
#     os.chdir(wd)
#
#     #get FI tform
#     source_image = reg_image_preprocess(source_fp, 1, img_type='AF')
#     target_image = reg_image_preprocess(target_fp, 1, img_type='AF')
#
#     param = parameter_files()
#
#     tmap_correction = register_elx_(
#         source_image.image,
#         target_image.image,
#         param.correction,
#         moving_mask=None,
#         fixed_mask=None,
#         output_dir=ts + project_name + "_tforms_FI_correction",
#         output_fn=ts + project_name + "_correction.txt",
#         logging=True)
#
#     #rois:
#     rois = ROIhandler(source_fp, 1, is_mask=False)
#     rois.get_rectangles_ijroi(ijroi_fp)
#     rois.draw_rect_mask(return_np=False)
#     rois = transform_mc_image_sitk(
#         rois.box_mask,
#         tmap_correction,
#         1,
#         from_file=False,
#         is_binary_mask=True)
#     rois = sitk.GetArrayFromImage(rois)
#
#     #get bounding rect. after transformation
#     roi_coords = mask_contours_to_boxes(rois)
#
#     #save csv of data
#     roi_coords.to_csv(ts + project_name + roi_name + ".csv", index=False)
#
#     #parse csv file into flexImaging xml for RECTANGLES!!!! only!!
#     output_flex_rects(
#         roi_coords,
#         imsres=ims_resolution,
#         imsmethod=ims_method,
#         roiname=roi_name + "_",
#         filename=ts + project_name + roi_name + ".xml")
#
#     if no_splits > 1:
#         split_boxes(
#             roi_coords,
#             no_splits=no_splits,
#             base_name=ts + project_name + roi_name,
#             ims_res=ims_resolution,
#             ims_method=ims_method,
#             roi_name=roi_name)
#
#     return
