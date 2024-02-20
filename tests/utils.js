const { exec } = require("child_process");


/**
 * Executes a lightning-cli command with the specified method and arguments.
 *
 * @param {string} method - The RPC method to call (e.g., 'getinfo').
 * @param {Object} args - An object containing the arguments for the method.
 */
function executeLightningCommand(method, args = {}, baseCliCommand) {
  // Construct the arguments string from the args object
  const argsString = Object.keys(args)
    .map((key) => `${key}=${args[key]}`)
    .join(" ");

  const command = `${baseCliCommand} -k ${method} ${argsString || ""}`;

  // console.log(`Executing command: ${command}`)

  return new Promise((resolve, reject) => {
    exec(command, (error, stdout, stderr) => {
      if (error) {
        reject(`exec error: ${error}`);
      }
      if (stderr) {
        reject(`stderr: ${stderr}`);
      }

      try {
        const result = JSON.parse(stdout);
        resolve(result);
      } catch (parseError) {
        console.error(`Error parsing JSON output: ${parseError}`);
        reject(`stdout: ${stdout}`);
      }
    });
  });
}

function generateRandomString(length=10) {
  const characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let result = '';
  const charactersLength = characters.length;
  for (let i = 0; i < length; i++) {
      result += characters.charAt(Math.floor(Math.random() * charactersLength));
  }
  return result;
}

module.exports = { executeLightningCommand, generateRandomString };
