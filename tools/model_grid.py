"""Put a raw input or reference scan on the grid of a RadWorld output, so that input, output and
reference can be shown side by side with a shared crosshair.

This follows ctgen/datasets/preprocess.py in the code release exactly: reorient to LPI, window and
min-max normalise to [-1, 1] (CT -1000..1000 HU, MR 0.5..99.5 percentiles), resample z first,
force x spacing == y spacing, pad to a square with the background value -1, resample x/y.
The result is mapped back to HU (CT) or to the percentile range (MR).
"""
import nibabel as nib
import numpy as np
import torch
import torch.nn.functional as F
from nibabel import orientations as ornt_


def resample_image(img, spacing, target_x, target_y, target_z):
    """Copied from ctgen/datasets/preprocess.py (release). img: (1, C, x, y, z)."""
    b, c, x, y, z = img.shape
    x_spacing, y_spacing, z_spacing = spacing
    target_z_spacing = z_spacing * z / target_z
    img = F.interpolate(img, size=(x, y, target_z), mode="trilinear", align_corners=False)
    if x_spacing != y_spacing:
        if x_spacing > y_spacing:
            resample_x = round(x * x_spacing / y_spacing)
            x_spacing = y_spacing
            img = F.interpolate(img, size=(resample_x, y, target_z), mode="trilinear", align_corners=False)
        else:
            resample_y = round(y * y_spacing / x_spacing)
            y_spacing = x_spacing
            img = F.interpolate(img, size=(x, resample_y, target_z), mode="trilinear", align_corners=False)
        b, c, x, y, z = img.shape
    if x != y:
        pad_x1 = (max(x, y) - x) // 2
        pad_x2 = max(x, y) - x - pad_x1
        pad_y1 = (max(x, y) - y) // 2
        pad_y2 = max(x, y) - y - pad_y1
        img = F.pad(img, (0, 0, pad_y1, pad_y2, pad_x1, pad_x2), value=-1)
        b, c, x, y, z = img.shape
    target_x_spacing = x_spacing * x / target_x
    target_y_spacing = y_spacing * y / target_y
    img = F.interpolate(img, size=(target_x, target_y, target_z), mode="trilinear", align_corners=False)
    return img, (target_x_spacing, target_y_spacing, target_z_spacing)


def to_model_grid(path, kind, out_path, like_path, size=(256, 256, 128)):
    """Resample `path` onto the model grid and save it with the affine of `like_path`."""
    img = nib.load(str(path))
    data = np.asanyarray(img.dataobj).astype(np.float32)
    tr = ornt_.ornt_transform(ornt_.io_orientation(img.affine), ornt_.axcodes2ornt(("L", "P", "I")))
    data = ornt_.apply_orientation(data, tr)
    zooms_in = [float(z) for z in img.header.get_zooms()[:3]]
    spacing = [0.0, 0.0, 0.0]
    for i, (ax, _) in enumerate(tr):
        spacing[int(ax)] = zooms_in[i]
    lo, hi = (-1000.0, 1000.0) if kind == "ct" else tuple(float(v) for v in np.percentile(data, [0.5, 99.5]))
    norm = (np.clip(data, lo, hi) - lo) / (hi - lo) * 2 - 1
    t = torch.tensor(norm)[None, None]
    t, new_spacing = resample_image(t, spacing, *size)
    arr = ((t[0, 0].numpy() + 1) / 2) * (hi - lo) + lo
    like = nib.load(str(like_path))
    out = nib.Nifti1Image(arr.astype(np.float32), like.affine)
    out.header.set_zooms(like.header.get_zooms()[:3])
    nib.save(out, str(out_path))
    return new_spacing, [round(float(z), 4) for z in like.header.get_zooms()[:3]]
