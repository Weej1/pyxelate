#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import warnings
import time as t
from pathlib import Path
from pyxelate import Pyxelate
from numpy import uint8
from skimage import io
from skimage import transform


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Pixelate images in a directory.'
    )
    parser.add_argument(
        '-f', '--factor',
        required=False, metavar='int', type=int, default=5, nargs='?',
        help='''The factor by which the image should be downscaled.
        Defaults to 5.'''
    )
    parser.add_argument(
        '-s', '--scaling',
        required=False, metavar='int', type=int, default=5, nargs='?',
        help='''The factor by which the generated image should be
        upscaled. Defaults to 5.'''
    )
    parser.add_argument(
        '-c', '--colors',
        required=False, metavar='2-32', type=int, default=8, nargs='?',
        help='''The amount of colors of the pixelated image. Defaults
        to 8.'''
    )
    parser.add_argument(
        '-d', '--dither',
        required=False, metavar='bool', type=str_as_bool, nargs='?',
        default=True, help='Allow dithering. Defaults to True.'
    )
    parser.add_argument(
        '-a', '--alpha',
        required=False, metavar='threshold', type=float, default=.6,
        nargs='?', help='''Threshold for visibility for images with
        alpha channel. Defaults to .6.'''
    )
    parser.add_argument(
        '-r', '--regenerate_palette',
        required=False, metavar='bool', type=bool, nargs='?',
        default=True, help='''Regenerate the palette for each image.
        Defaults to True.'''
    )
    parser.add_argument(
        '-t', '--random_state',
        required=False, metavar='int', type=int, default=0, nargs='?',
        help='''Sets the random state of the Bayesian Gaussian Mixture.
        Defaults to 0.'''
    )
    parser.add_argument(
        '-i', '--input',
        required=False, metavar='path', type=str, default='', nargs='?',
        help='''Path to single image or directory containing images for
        processing. Defaults <cwd>.'''
    )
    parser.add_argument(
        '-o', '--output',
        required=False, metavar='path', type=str, default='', nargs='?',
        help='''Path to the directory where the pixelated images are
        stored. Defaults to <cwd>/pyxelated'''
    )
    parser.add_argument(
        '-w', '--warnings',
        required=False, metavar='bool', type=str_as_bool, nargs='?',
        default=True, help='''Outputs non-critical library warnings.
        Defaults to True.'''
    )
    return parser.parse_args()


def str_as_bool(val):
    # Interpret the string input as a boolean
    if val.lower() in ("false", "none", "no", "0"):
        return False
    return True


# Exclude hidden files and directories
f_excluded = 0

def exclude_hidden(elm):
    global f_excluded
    if not any(i.startswith('.') for i in elm.parts):
        return elm
    f_excluded += 1
    return False


 # Exclude directories and files without extension
def with_extension(elm):
    global f_excluded
    if elm.is_file() and '.' in elm.name:
        return elm
    f_excluded += 1
    return False


def get_file_list(path):
    path = Path(path)
    if path.is_dir():
        # Get all files and directories
        tree = list(path.glob('**/*'))
        # Filter files and directories
        tree = list(filter(exclude_hidden, tree))
        file_names = list(filter(with_extension, tree))
        return file_names
    elif path.is_file() and '.' in path.name:
        return [path]
    else:
        print("Path points to " + red("non image") + " file.")
        sys.exit(1)


def parse_path(file):
    f_name, f_ext = str(file).rsplit('.', 1)
    re = str(Path(args.input))
    if re == '.':
        f_name = '/' + f_name
    try:
        f_path, f_name = f_name.rsplit('/', 1)
    except ValueError:
        f_path = ""
    if re == str(file):
        f_path = ""
    f_path = f_path.replace(re, "")
    f_path += '/' if f_path else ''
    return [f_path, f_name, f_ext]


# Define CLI colors and create functions
def style_def(func, ansi):
    exec(f'''def {func}(input):
        return "{ansi}" + str(input) + "\u001b[0m"
    ''', globals())

style_def('green', '\u001b[32m')
style_def('red', '\u001b[31m')
style_def('mag', '\u001b[35m')
style_def('dim', '\u001b[37;2m')


# Status bar logic
cur_file = 0
warn_cnt = 0
err_cnt = 0
time_img = []
avg_last_vals = 10
t_up = '\x1b[1A'
t_erase = '\x1b[2K'
bar_rmv = '\n' + t_erase + t_up + t_erase

def sec_to_time(sec):
    n, m, s = 0, 0, 0
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}"

def bar_redraw(last=False):
    t_pass = round(t.process_time())
    i_cur = cur_file
    # Print bar
    percent = round(i_cur / all_files * 100, 1)
    p_int = round(i_cur / all_files * 100) // 2
    b = "[ " + "•" * (p_int) + dim("-") * (50 - p_int) + " ] "
    b += str(percent) + " %"
    print(b)
    # Print status
    r = "Done " + green(str(i_cur)) + '/' + str(all_files) + dim(" | ")
    if args.warnings:
        r += "Warnings: " + mag(str(warn_cnt)) + dim(" | ")
    r += "Errors: " + red(str(err_cnt)) + dim(" | ")
    r += "Elapsed: " + sec_to_time(t_pass) + dim(" | ") + "Remaining: "
    # Remaining time. Averaging requires at least 1 value
    if len(time_img) > 0 and not last:
        t_avg = sum(time_img) / len(time_img)
        rem = round(t_avg * (all_files - i_cur))
        r += sec_to_time(rem)
    else:
        r += "Calculating..." if not last else sec_to_time(0)
    # Adding escape codes depending on the passed argument
    if last:
        r = bar_rmv + r
    else:
        # Raise the carriage two lines up and return it
        r = r + t_up * 2 + '\r'
    print(r)


def print_warn(warn):
    if str(warn) and args.warnings:
        re = "/".join([o_path, o_base, f_name]) + '.' + f_ext
        warn = str(warn).replace(re, "").strip().capitalize()
        print(bar_rmv + mag("\tWarning: ") + warn)
        bar_redraw()

def print_err(err):
    if str(err):
        re = "/".join([o_path, o_base, f_name]) + '.' + f_ext
        err = str(err).replace(re, "").strip().capitalize()
        print(bar_rmv + red("\tError: ") + err)
        bar_redraw()

if __name__ == "__main__":
    # Get arguments and file list
    args = parse_arguments()
    image_files = get_file_list(args.input)
    all_files = len(image_files)

    # Use the output directory defined by args
    if not args.output:
        output_dir = Path.cwd() / "pyxelated"
        output_dir.mkdir(exist_ok=True)
    else:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

    # At least one relevant file is required to run
    if image_files:
        print(green(len(image_files)) + " relevant files found | " +
            red(f_excluded) + " excluded")
    else:
        print(red(len(image_files)) + " relevant files found")
        sys.exit(1)

    # Get input and output paths
    # And display some information at the start
    input_dir = Path(args.input) if args.input else Path.cwd()
    if "/" in str(output_dir):
        o_path, o_base = str(output_dir).rsplit('/', 1)
        print("Writing files to   " + dim(o_path + '/') + o_base)        
    else:
        print("Reading files from " + str(output_dir))
    
    if "/" in str(input_dir):
        i_path, i_base = str(input_dir).rsplit('/', 1)    
        print("Reading files from " + dim(i_path + '/') + i_base)
    else:
        print("Reading files from " + dim(str(Path.cwd())) + "/" + str(input_dir))

    # Height and width are getting set per image, this are just placeholders
    p = Pyxelate(1, 1, color=args.colors, dither=args.dither,
        alpha=args.alpha, regenerate_palette=args.regenerate_palette,
        random_state=args.random_state)

    # Loop over all images in the directory
    for image_file in image_files:
        # Get the path, file name, and extension
        base = str(image_file.stem) + ".png"
        outfile = output_dir / base
        f_path, f_name, f_ext = parse_path(image_file)

        # Get the time of the last iteration to calculate the remaining
        if 'img_end' in globals():
            if len(time_img) == avg_last_vals:
                del time_img[0]
                time_img.append(round(img_end - img_start, 1))
            else:
                time_img.append(round(img_end - img_start, 1))
        img_start = t.time()

        # The file format must be supported by skimage
        try:
            image = io.imread(image_file)
        except ValueError:
            # When the file is not an image just move to the next file
            print(bar_rmv + "\tSkipping " + red("unsupported") +
                ":\t" + dim(f_path) + f_name + '.' + red(f_ext))
            bar_redraw()
            continue

        print(bar_rmv + "\tProcessing image:\t" + dim(f_path) +
            f_name + '.' + f_ext)

        # Redraw status bar
        bar_redraw()

        # Get image dimensions
        height, width, _ = image.shape

        # Apply the dimensions to Pyxelate
        p.height = height // args.factor
        p.width = width // args.factor

        try:
            warnings.filterwarnings("error")
            pyxelated = p.convert(image)
        except KeyboardInterrupt:
            print(bar_rmv + "Cancelled with " + red("Ctrl+C"))
            bar_redraw(1)
            sys.exit(0)
        except IndexError as e:
            # When the file is not an image just move to the next file
            err_cnt += 1
            print_err(e)
            bar_redraw()
            continue
        except BaseException as e:
            warn_cnt += 1
            print_warn(e)
            warnings.filterwarnings("ignore")
            pyxelated = p.convert(image)

        # Scale the image up if so requested
        if args.scaling > 1:
            pyxelated = transform.resize(pyxelated, (
                (height // args.factor) * args.scaling,
                (width // args.factor) * args.scaling),
                anti_aliasing=False, mode='edge',
                preserve_range=True, order=0
            )

        # Finally save the image
        try:
            warnings.filterwarnings("error")
            io.imsave(outfile, pyxelated.astype(uint8))
        except KeyboardInterrupt:
            print(bar_rmv + "Cancelled with " + red("Ctrl+C"))
            bar_redraw(1)
            sys.exit(0)
        except BaseException as e:
            warn_cnt += 1
            print_warn(e)
            warnings.filterwarnings("ignore")
            io.imsave(outfile, pyxelated.astype(uint8))

        img_end = t.time()
        cur_file += 1 # Only count up if the image was successfully processed

    bar_redraw(1)
