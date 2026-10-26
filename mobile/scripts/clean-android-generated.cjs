"use strict";

const fs = require("node:fs");
const path = require("node:path");

const mobileRoot = path.resolve(__dirname, "..");
const packageJsonPath = path.join(mobileRoot, "package.json");

if (!fs.existsSync(packageJsonPath)) {
  console.error("Safety check failed: mobile package.json not found.");
  process.exit(1);
}

const packageJson = JSON.parse(
  fs.readFileSync(packageJsonPath, "utf8")
);

if (packageJson.name !== "fieldops-mobile") {
  console.error(
    "Safety check failed: this is not the FieldOps mobile workspace."
  );
  process.exit(1);
}

const generatedFolders = [
  ".expo",
  "node_modules/.cache",
  "android/.gradle",
  "android/build",
  "android/app/build",
  "android/app/.cxx",

  "node_modules/react-native-reanimated/android/build",
  "node_modules/react-native-reanimated/android/.cxx",

  "node_modules/react-native-worklets/android/build",
  "node_modules/react-native-worklets/android/.cxx",

  "node_modules/expo-modules-core/android/build",
  "node_modules/expo-modules-core/android/.cxx",

  "node_modules/react-native-gesture-handler/android/build",
  "node_modules/react-native-gesture-handler/android/.cxx",

  "node_modules/react-native-screens/android/build",
  "node_modules/react-native-screens/android/.cxx",

  "node_modules/expo-sqlite/android/build",
  "node_modules/expo-sqlite/android/.cxx"
];

function getDirectorySize(directory) {
  let total = 0;

  let entries;

  try {
    entries = fs.readdirSync(directory, {
      withFileTypes: true
    });
  } catch {
    return 0;
  }

  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);

    try {
      if (entry.isDirectory()) {
        total += getDirectorySize(fullPath);
      } else if (entry.isFile()) {
        total += fs.statSync(fullPath).size;
      }
    } catch {
      // Ignore files that are inaccessible during inspection.
    }
  }

  return total;
}

const deleteMode = process.argv.includes("--delete");
let totalBytes = 0;
let removedCount = 0;

console.log(
  deleteMode
    ? "Cleaning generated Android build files..."
    : "DRY RUN: inspecting generated folders only."
);

for (const relativePath of generatedFolders) {
  const targetPath = path.resolve(mobileRoot, relativePath);
  const relativeCheck = path.relative(mobileRoot, targetPath);

  if (
    relativeCheck === "" ||
    relativeCheck === ".." ||
    relativeCheck.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relativeCheck)
  ) {
    console.error(`Safety check skipped: ${relativePath}`);
    continue;
  }

  if (!fs.existsSync(targetPath)) {
    continue;
  }

  let stat;

  try {
    stat = fs.lstatSync(targetPath);
  } catch {
    continue;
  }

  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    console.log(`Skipped non-directory: ${relativePath}`);
    continue;
  }

  const sizeBytes = getDirectorySize(targetPath);
  totalBytes += sizeBytes;

  const sizeMB = (sizeBytes / (1024 * 1024)).toFixed(1);

  if (deleteMode) {
    try {
      fs.rmSync(targetPath, {
        recursive: true,
        force: true
      });

      removedCount += 1;
      console.log(`Removed: ${relativePath} (${sizeMB} MB)`);
    } catch (error) {
      console.error(`Could not remove: ${relativePath}`);
      console.error(error.message);
    }
  } else {
    console.log(`Found: ${relativePath} (${sizeMB} MB)`);
  }
}

console.log(
  `\nTotal identified: ${(totalBytes / (1024 ** 3)).toFixed(2)} GB`
);

if (deleteMode) {
  console.log(`Folders removed: ${removedCount}`);
} else {
  console.log(
    "\nNothing was deleted. Review the list before running with --delete."
  );
}