#!/usr/bin/env python3

import sys
import time
import toml
import numpy as np
from tqdm import tqdm
from PIL import Image
from pathlib import Path
from click import clear, echo, style, secho
from multiprocessing import Pool
from matplotlib import pyplot as plt
from numba import njit, jit
from typing import List, Tuple

conf = toml.load("config.toml")
DATA_SUBSET = 50
time_data = {}

# timeit: decorator to time functions
def timeit(f):
    def timed(*args, **kwargs):
        ts = time.time()
        result = f(*args, **kwargs)
        te = time.time()

        """
        echo(
            style("[DEBUG] ", fg="green") + f"{f.__name__}  {((te - ts) * 1000):.2f} ms"
        )
        """

        if f.__name__ in time_data.keys():
            time_data[f.__name__].append((te - ts) * 1000)
        else:
            time_data[f.__name__] = [(te - ts) * 1000]

        return result

    return timed


@njit(fastmath=True)
def cumsum(a):
    a = iter(a)
    b = [next(a)]
    for i in a:
        b.append(b[-1] + i)

    return np.array(b)


@njit
def histogram(img_array):
    """
    >> h=zeros(256,1);              OR    >> h=zeros(256,1);
    >> for l = 0 : 255                    >> for l = 0 : 255
         for i = 1 : N                          h(l +1)=sum(sum(A == l));
            for j = 1 : M                    end
                if (A(i,j) == l)          >> bar(0:255,h);
                    h(l +1) = h(l +1) +1;
                end
            end
        end
    end
    >> bar(0:255,h);
    """

    # Create blank histpgram
    hist = np.zeros(256)

    # Get size of pixel array
    N = len(img_array)

    for l in range(256):
        for i in range(N):

            # Loop through pixels to calculate histogram
            if img_array.flat[i] == l:
                hist[l] += 1

    return hist


@njit(fastmath=True)
def calculate_histogram(img_array: np.array) -> np.array:
    """
    g1(l) = ∑(l, k=0) pA(k) ⇒ g1(l)−g1(l −1) = pA(l) = hA(l)/NM (l = 1,...,255)

    geA(l) = round(255g1(l))
    """

    flat = img_array.flatten()

    hist = histogram(flat)
    cs = cumsum(hist)

    nj = (cs - cs.min()) * 255

    N = cs.max() - cs.min()

    cs = nj / N

    cs_casted = cs.astype(np.uint8)

    equalized = cs_casted[flat]
    img_new = np.reshape(equalized, img_array.shape)

    return hist, histogram(equalized), img_new


def select_channel(img_array: np.array, color: str = "", log_time=None) -> np.array:

    if color == "red":
        return img_array[:, :, 0]

    elif color == "green":
        return img_array[:, :, 1]

    elif color == "blue":
        return img_array[:, :, 2]

    else:
        # Default to using the default greyscaling Pillow does
        img = Image.fromarray(img_array, "L")

        return np.array(img)


@timeit
@njit
def season_noise(img_array, strength: int) -> np.array:
    s_vs_p = 0.5
    out = np.copy(img_array)

    # Generate Salt '1' noise
    num_salt = np.ceil(strength * img_array.size * s_vs_p)

    for i in range(int(num_salt)):
        x = np.random.randint(0, img_array.shape[0] - 1)
        y = np.random.randint(0, img_array.shape[1] - 1)
        out[x][y] = 0

    # Generate Pepper '0' noise
    num_pepper = np.ceil(strength * img_array.size * (1.0 - s_vs_p))

    for i in range(int(num_pepper)):
        x = np.random.randint(0, img_array.shape[0] - 1)
        y = np.random.randint(0, img_array.shape[1] - 1)
        out[x][y] = 0

    return out


@timeit
@njit
def gaussian_noise(img_array: np.array, sigma: int) -> np.array:
    mean = 0.0

    noise = np.random.normal(mean, sigma, img_array.size)
    shaped_noise = noise.reshape(img_array.shape)

    gauss = img_array + shaped_noise

    return gauss


@njit(fastmath=True)
def apply_filter(img_array, img_filter):

    rows, cols = img_array.shape
    height, width = img_filter.shape

    output = np.zeros((rows - height + 1, cols - width + 1))

    for rr in range(rows - height + 1):
        for cc in range(cols - width + 1):
            for hh in range(height):
                for ww in range(width):
                    imgval = img_array[rr + hh, cc + ww]
                    filterval = img_filter[hh, ww]
                    output[rr, cc] += imgval * filterval

    return output


@timeit
def linear_filter(
    img_array: np.array, mask_size: int, weights: List[List[int]]
) -> np.array:

    filter = np.array(weights)
    linear = apply_filter(img_array, filter)

    return linear


@njit(fastmath=True)
def apply_median_filter(img_array: np.array, img_filter: np.array) -> np.array:

    rows, cols = img_array.shape
    height, width = img_filter.shape

    pixel_values = np.zeros(img_filter.size ** 2)
    output = np.zeros((rows - height + 1, cols - width + 1))

    for rr in range(rows - height + 1):
        for cc in range(cols - width + 1):

            p = 0
            for hh in range(height):
                for ww in range(width):

                    pixel_values[p] = img_array[hh][ww]
                    p += 1

            # Sort the array of pixels inplace
            pixel_values.sort()

            # Assign the median pixel value to the filtered image.
            output[rr][cc] = pixel_values[p // 2]

    return output


@timeit
def median_filter(
    img_array: np.array, mask_size: int, weights: List[List[int]]
) -> np.array:

    filter = np.array(weights)
    median = apply_median_filter(img_array, filter)

    return median


def export_image(img_arr: np.array, filename: str) -> None:
    img = Image.fromarray(img_arr)
    img = img.convert("L")
    img.save(conf["OUTPUT_DIR"] + filename + ".BMP")


def export_plot(img_arr: np.array, filename: str) -> None:
    _ = plt.hist(img_arr, bins=256, range=(0, 256))
    plt.title(filename)
    plt.savefig(conf["OUTPUT_DIR"] + filename + ".png")
    plt.close()


def get_image_data(filename: Path, log_time=None) -> np.array:
    with Image.open(filename) as img:
        return np.array(img)


def apply_operations(img_file):
    try:

        color_img = get_image_data(img_file)

        # Grey scale image
        img = select_channel(color_img, color=conf["COLOR_CHANNEL"])

        # Create salt and peppered noise image
        salt_and_pepper = season_noise(img, conf["SALT_PEPPER_STRENGTH"])

        # Create gaussian noise image
        gauss = gaussian_noise(img, conf["GAUSS_NOISE_STRENGTH"])

        # Apply linear filter to image
        linear = linear_filter(img, conf["LINEAR_MASK"], conf["LINEAR_WEIGHTS"])

        # Apply median filter to image
        median = median_filter(img, conf["MEDIAN_MASK"], conf["MEDIAN_WEIGHTS"])

        # Calculate histogram for image
        histogram, equalized, equalized_image = calculate_histogram(img)

        """
        echo(
            style(f"[DEBUG:{img_file.stem}] ", fg="green")
            + f"exporting plots and images for {img_file.stem}..."
        )
        """

        export_image(salt_and_pepper, "salt_and_pepper_" + img_file.stem)

        export_image(gauss, "gaussian_" + img_file.stem)

        export_image(equalized_image, "equalized_" + img_file.stem)

        export_image(linear, "linear_" + img_file.stem)

        export_image(median, "median_" + img_file.stem)

        # export_plot(histogram, "histogram_" + img_file.stem)

        # export_plot(equalized, "histogram_equalized_" + img_file.stem)

        return img_file.stem

    except Exception as e:
        return style(f"[ERROR:{img_file.stem}] ", fg="red") + str(e)


def parallel_operations(files):
    echo(
        style("[INFO] ", fg="green")
        + f"initilizing process pool ({conf['NUM_OF_PROCESSES']})"
    )
    with Pool(conf["NUM_OF_PROCESSES"]) as p:
        with tqdm(total=len(files)) as pbar:
            for _, res in tqdm(enumerate(p.imap(apply_operations, files))):
                pbar.write(
                    style(f"[INFO:{res}] ", fg="cyan")
                    + f"performing operations on: {style(res, fg='cyan')}"
                )
                pbar.update()


def main(argv: List[str]):

    clear()

    base_path = Path(conf["DATA_DIR"])
    echo(style("[INFO] ", fg="green") + f"image directory: {str(base_path)}")

    files = list(base_path.glob("*.BMP"))

    Path(conf["OUTPUT_DIR"]).mkdir(parents=True, exist_ok=True)

    time_data = {}

    t0 = time.time()

    # [!!!] Only for development
    # files = files[:DATA_SUBSET]

    parallel_operations(files)

    t_delta = time.time() - t0

    for k, v in time_data.items():
        echo(
            style("[INFO] ", fg="green")
            + "average time data: "
            + style(f"{k} : {(v / len(files)):.2f} ms", fg="red")
        )

    print()
    secho(f"[INFO] Total time: {t_delta:.2f} (s)", fg="cyan")


if __name__ == "__main__":
    main(sys.argv)
