import os
import shutil
import cv2
import glob
import pandas as pd
from libra.data_generation.dataset_labelmatcher import get_similar_column
from libra.data_generation.grammartree import get_value_instruction

# Preprocesses images from images to median of heighs/widths
def setwise_preprocessing(data_path, new_folder=True):
    training_path = data_path + "/training_set"
    testing_path = data_path + "/testing_set"

    heights = []
    widths = []
    classification = 0

    # first dictionary is training and second is testing set
    paths = [training_path, testing_path]
    dict = []
    data_size = []
    for index in range(2):
        info = process_class_folders(paths[index])
        data_size.append(len(info[0]))
        heights += info[0]
        widths += info[1]
        classification += info[2]
        dict.append(info[3])

    classification = int(classification/2)
    height, width = calculate_medians(heights, widths)

    # resize images
    for index, p in enumerate(paths):
        for class_folder, images in dict[index].items():
            for image_name, image in images.items():
                dict[index][class_folder][image_name] = process_color_channel(
                    image, height, width)
        if new_folder:
            folder_names = ["proc_training_set", "proc_testing_set"]
            create_folder(data_path, folder_names[index])
            for class_folder, images in dict[index].items():
                add_resized_images(
                    data_path + "/" + folder_names[index],
                    class_folder,
                    images)
        else:
            for class_folder, images in dict[index].items():
                replace_images(p + "/" + class_folder, images)

    return {"num_categories": classification, 
            "height": height, 
            "width": width, 
            "train_size": data_size[0], 
            "test_size": data_size[1]}


# processes a csv_file containing image paths and creates a testing/training 
# folders with resized images inside the same directory as the csv file
def csv_preprocessing(csv_file, 
                      data_path, 
                      instruction, 
                      image_column, 
                      training_ratio):
    df = pd.read_csv(csv_file)
    if instruction is None:
        raise BaseException("Instruction was not given.")
    label = get_similar_column(get_value_instruction(instruction), df)
    avoid_directories = ["proc_training_set", "proc_testing_set"]
    data_paths = [data_path + "/" + d for d in os.listdir(data_path) 
                  if os.path.isdir(data_path + "/" + d) and d not in avoid_directories]

    # get file extension
    _, file_extension = os.path.splitext(os.listdir(data_paths[0])[0])

    # select random row to find which column is image path
    random_row = df.sample()
    need_file_extension = False
    path_included = False

    while image_column is None:
        for column, value in random_row.iloc[0].items():
            if type(value) is str:
                if os.path.exists(value):
                    path_included = True
                    image_column = column
                    break
                # add file extension if not included
                file = value if file_extension in value else value + file_extension

                # look through all data_paths for file
                for path in data_paths:
                    if os.path.exists(path + "/" + file):
                        if file_extension in file:
                            need_file_extension = True
                        image_column = column
                        break
            if image_column is not None:
                break

    else:
        if os.path.exists(df.iloc[0][image_column]):
            path_included = True
        elif file_extension not in df.iloc[0][image_column]:
            need_file_extension = True

    df = df[[image_column, label]].dropna()

    if need_file_extension:
        df[image_column] = df[image_column] + file_extension
    heights = []
    widths = []
    classifications = df[label].nunique()
    image_list = []

    # get the median heights and widths
    for index, row in df.iterrows():
        for path in data_paths:
            p = row[image_column] if path_included else path + "/" + row[image_column]
            img = cv2.imread(p)
            if img is not None:
                break
        else:
            raise BaseException(f"{row[image_column]} could not be found in any directories.")
        image_list.append(img)
        heights.append(img.shape[0])
        widths.append(img.shape[1])

    height, width = calculate_medians(heights, widths)

    # create training and testing folders
    create_folder(data_path, "proc_training_set")
    create_folder(data_path, "proc_testing_set")
    # create classification folders
    for classification in df[label].unique():
        create_folder(data_path + "/proc_training_set", classification)
        create_folder(data_path + "/proc_testing_set", classification)

    data_size = [0,0]
    # save images into correct folder
    for index, row in df.iterrows():
        # resize images
        img = process_color_channel(image_list[index], height, width)
        p = "proc_" + (os.path.basename(row[image_column]) 
                            if path_included else row[image_column])
        if (index / df.shape[0]) < training_ratio:
            data_size[0] += 1
            save_image(data_path + "/proc_training_set", img, p, row[label])
        else:
            data_size[1] += 1
            save_image(data_path + "/proc_testing_set", img, p, row[label])

    return {"num_categories": classifications, 
            "height": height, 
            "width": width, 
            "train_size": data_size[0], 
            "test_size": data_size[1]}


# preprocesses images when given a folder containing class folders
def classwise_preprocessing(data_path, training_ratio):
    info = process_class_folders(data_path)
    height, width = calculate_medians(info[0], info[1])
    num_classifications = info[2]
    img_dict = info[3]

    # create training and testing folders
    create_folder(data_path, "proc_training_set")
    create_folder(data_path, "proc_testing_set")

    # create classification folders
    for classification in img_dict.keys():
        create_folder(data_path + "/proc_training_set", classification)
        create_folder(data_path + "/proc_testing_set", classification)

    data_size = [0,0]
    for class_folder, images in img_dict.items():
        count = 0
        for image_name, image in images.items():
            resized_img = process_color_channel(image, height, width)
            if count / len(images) < training_ratio:
                data_size[0] += 1
                save_image(data_path + "/proc_training_set",
                           resized_img,
                           "proc_" + image_name,
                           class_folder)
            else:
                data_size[1] += 1
                save_image(data_path + "/proc_testing_set",
                           resized_img,
                           "proc_" + image_name,
                           class_folder)
            count += 1

    return {"num_categories": num_classifications, 
            "height": height, 
            "width": width, 
            "train_size": data_size[0], 
            "test_size": data_size[1]}


# process a class folder by getting return a list of all the heights and widths
def process_class_folders(data_path):
    heights = []
    widths = []
    num_classifications = 0
    img_dict = {}
    avoid_directories = ["proc_training_set", "proc_testing_set"]

    for class_folder in os.listdir(data_path):
        if not os.path.isdir(data_path + "/" + class_folder) or class_folder in avoid_directories:
            continue

        folder_dict = {}
        folder_height = []
        folder_width = []

        for image in os.listdir(data_path + "/" + class_folder):
            try:
                if image == ".DS_Store":
                    continue
                img = cv2.imread(data_path + "/" + class_folder + "/" + image)
                folder_height.append(img.shape[0])
                folder_width.append(img.shape[1])
                folder_dict[image] = img
            except BaseException:
                break
        else:
            heights += folder_height
            widths += folder_width
            img_dict[class_folder] = folder_dict
            num_classifications += 1

    return [heights, widths, num_classifications, img_dict]


# creates a folder with the given folder name and fills the folders
# with the images given
def add_resized_images(data_path, folder_name, images):
    # create processed folder
    os.mkdir(data_path + "/proc_" + folder_name)
    # add images to processed folder
    for img_name, img in images.items():
        cv2.imwrite(
            data_path +
            "/proc_" +
            folder_name +
            "/proc_" +
            img_name,
            img)


# writes an image into the given path
def replace_images(data_path, loaded_shaped):
    for img_name, img in loaded_shaped.items():
        cv2.imwrite(data_path + "/" + img_name, img)


# creates a folder in the given path with the given folder name
def create_folder(path, folder_name):
    folder_name = "/" + folder_name
    if os.path.isdir(path + folder_name):
        shutil.rmtree(path + folder_name)
    os.mkdir(path + folder_name)


# saves an image to the given path inside the classification folder
# specified with the img_name
def save_image(path, img, img_name, classification):
    cv2.imwrite(
        path + "/" + classification + "/" + img_name,
        img)

# calculates the medians of the given lists of height and widths
def calculate_medians(heights, widths):
    heights.sort()
    widths.sort()
    height = heights[int(len(heights) / 2)]
    width = widths[int(len(widths) / 2)]
    return height, width


# resizes the image with the given height and width
def process_color_channel(img, height, width):
    chanels = [chanel for chanel in cv2.split(img)]

    for index, chanel in enumerate(chanels):
        if chanel.shape[0] > height:
            chanel = cv2.resize(
                chanel,
                dsize=(
                    chanel.shape[1],
                    height),
                interpolation=cv2.INTER_CUBIC)
        else:
            chanel = cv2.resize(
                chanel,
                dsize=(
                    chanel.shape[1],
                    height),
                interpolation=cv2.INTER_AREA)
        if chanel.shape[1] > width:
            chanel = cv2.resize(
                chanel,
                dsize=(
                    width,
                    height),
                interpolation=cv2.INTER_CUBIC)
        else:
            chanel = cv2.resize(
                chanel,
                dsize=(
                    width,
                    height),
                interpolation=cv2.INTER_AREA)
        chanels[index] = chanel

    return cv2.merge(chanels)


# Seperates the color channels and then reshapes each of the channels to
# (224, 224)
# def processColorChanel(img):
#     b, g, r = cv2.split(img)
#     # seperating each value into a color channel and resizing to a standard
#     # size of 224, 224, 3 <- because of RGB color channels. If it's not 3
#     # color channels it'll pad with zeroes
#     b = cv2.resize(b, dsize=(224, 224), interpolation=cv2.INTER_CUBIC)
#     g = cv2.resize(g, dsize=(224, 224), interpolation=cv2.INTER_CUBIC)
#     r = cv2.resize(r, dsize=(224, 224), interpolation=cv2.INTER_CUBIC)
#     img = cv2.merge((b, g, r))
#     return img

def set_distinguisher(data_path, read_mode):
    if read_mode is not None:
        if read_mode == "setwise":
            return {"read_mode": "setwise"}
        elif read_mode == "classwise":
            return {"read_mode":"classwise"}
        elif read_mode == "pathwise" or read_mode == "namewise":
            csv_path = glob.glob(data_path + "/*.csv")
            if len(csv_path) == 1:
                return {"read_mode":"pathwise or namewise", "csv_path":csv_path[0]}
            elif len(csv_path) > 1:
                raise BaseException(f"Too many csv files in directory: {[os.path.basename(path) for path in csv_path]}")
        else:
            raise BaseException(f"{read_mode}, is an invalid read mode.")

    # check if setwise
    if os.path.isdir(data_path + "/training_set") and os.path.isdir(data_path + "/testing_set"):
        return {"read_mode":"setwise"}

    # check if contains a csv file
    csv_path = glob.glob(data_path + "/*.csv")
    if len(csv_path) == 1:
        return {"read_mode":"pathwise or namewise", "csv_path":csv_path[0]}
    elif len(csv_path) > 1:
        raise BaseException(f"Too many csv files in directory: {[os.path.basename(path) for path in csv_path]}")

    return {"read_mode":"classwise"}