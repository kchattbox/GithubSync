#!/usr/bin/python3
import requests
import base64
import os

class GitHubRepo:
    """
    This GitHubRepo class will be the API that our program will use to keep track of 
    files we want to add and provide an interface with the GitHub API to 
    
    """

    _apiBaseURL = "https://api.github.com/"
    masterFile = ".master"
    ref = "main"
    fileMode = "100644"
    directoryMode = "040000"
    branch = "main"
    emptyTreeSha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def __init__(self, username, repoName, accessToken):
        self.username = username
        self.repoName = repoName
        self.accessToken = accessToken
        self.addedFiles = []
        self.homeDir = os.path.expanduser('~')
    
    @staticmethod
    def createRemoteRepo(username, repoName, accessToken, repoDescription=""):
        url = GitHubRepo._apiBaseURL + f"user/repos"
        requestHeader = {
            "Authorization": f"token {accessToken}"
        }

        requestData = {
            "name": repoName,
            "description": repoDescription,
            "auto_init": "true"
        }

        res = requests.post(url, headers=requestHeader, json=requestData)

        if res.status_code == 201:
            # print(f"LOG: Created GitHubRepo {repoName} sucessfully")
            return GitHubRepo(username, repoName, accessToken)
        else:
            raise Exception(f"Request to {url} receieved a {res.status_code} response and could not create the GitHub repo. Message = {res.json()}")

    def _queryAPI(self, url, headers={}, json={}, method="get", wantJson=True):
        headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.accessToken}"
        })

        if method == "get":
            res = requests.get(url, headers=headers, json=json)

        elif method == "post":
            res = requests.post(url, json=json, headers=headers)

        elif method == "put":
            res = requests.put(url, json=json, headers=headers)

        elif method == "patch":
            res = requests.patch(url, headers=headers, json=json)

        else:
            raise Exception(f"{method} is not an implemented request method")

        # if res.status_code != 200:
            # raise Exception(f"Contents could not be retrieved. {res.status_code}, {res.text}, {url}")
        # print(f"LOG: Received response {res.status_code}")
        # print("LOG: Content successfully retrieved")

        if wantJson == False:
            return res
        else:
            return res.json()

    def _getPreviousCommit(self):
        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/git/refs/heads/{self.branch}", wantJson=False)
        if response.status_code == 409:
            return None
        else:
            return response.json()["object"]["sha"]

    def _getBranchTree(self, previousCommit, branch="main"):
        url = f"https://api.github.com/repos/{self.username}/{self.repoName}/commits/{previousCommit}"
        treeUrl = self._queryAPI(url)['commit']['tree']['url']
        return self._queryAPI(treeUrl)['sha']

    def _createNewBlob(self, content):
        blob_data =  {
            "content": base64.b64encode(content.encode()).decode(),
            "encoding": "base64"
        }

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.accessToken}"
        }

        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/git/blobs", json=blob_data, method="post")
        return response["sha"]

    def _createNewTreeBlob(self, path, fileType, sha): # should be self.fileMode or self.directoryMode
        return {
            "path": path,
            "mode": fileType,
            "type": "blob",
            "sha": sha
        }

    def _createTree(self, blobs):
        tree_data = {
            "tree": blobs
        }

        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/git/trees", json=tree_data, method="post")
        return response["sha"]

    def _updateTree(self, treeSha, newBlobs): # newBlobs should be an array of tree blobs!
        tree_data = {
            "base_tree": treeSha,
            "tree": newBlobs
        }

        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/git/trees", json=tree_data, method="post")
        return response["sha"]

    def _commitTree(self, treeSha, previousCommitSha, message=""):
        commit_data = {
            "message": message,
            "tree": treeSha,
        }
        if previousCommitSha != None:
            commit_data["parents"] = [previousCommitSha]

        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/git/commits", json=commit_data, method="post")
        return response["sha"]

    def _updateBranchReference(self, commitSha, force=False):
        reference_data = {
            "sha": commitSha,
        }

        if force == True:
            reference_data["force"] = "true"

        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/git/refs/heads/{self.branch}", json=reference_data, method="patch")

    def _createBranch(self, branchName="main"):

        self._createFile(path=".master", branch=branchName) # this should create the branch

        commitSha = self._commitTree(self.emptyTreeSha, None, message="Initial Commit")

        self._updateBranchReference(commitSha)

    def _createFile(self, contents="", path="", message="", branch="main"):
        file_data = {
            "branch": branch,
            "message": message,
            "content": base64.b64encode(contents.encode()).decode()
        } 
        
        response = self._queryAPI(f"https://api.github.com/repos/{self.username}/{self.repoName}/contents/{path}", json=file_data, method="put")
        return response["content"]["sha"]

    def getFile(self, path):
        url = self._apiBaseURL + f"repos/{self.username}/{self.repoName}/contents/{path}?ref={self.ref}"
        # url = f"https://raw.githubusercontent.com/{self.username}/GithubSync/refs/heads/main/{path}"

        jsonData = self._queryAPI(url)

        if isinstance(jsonData, list):
            raise Exception(f"{path} is a directory!")
    
        return base64.b64decode(jsonData['content']).decode('utf-8')

    def readRemoteFiles(self):
        masterFile = self.getFile(f"{self.masterFile}").strip().split('\n')
        fileInfo = masterFile[1:]
        registeredFiles = {}
        for i in range(len(fileInfo)):
            temp = fileInfo[i].split()
            registeredFiles[temp[0]] = {
                "localPath": temp[2].replace('~', self.homeDir),
                "contents": self.getFile(temp[0])
            }
        return registeredFiles
    
    def readLocalFiles(self):
        masterFile = open(".master", "r")
        fileInfo = masterFile.read().strip().split('\n')[1:]
        masterFile.close()
        registeredFiles = {}
        for i in range(len(fileInfo)):
            if fileInfo[i].strip() == "":
                continue
            temp = fileInfo[i].split()
            localPath = temp[2].replace('~', self.homeDir)
            file = open(localPath, "r")
            registeredFiles[temp[0]] = {
                "localPath": localPath,
                "contents": file.read()
            }
            file.close()

        return registeredFiles

    def writeLocalFiles(self, registeredFiles):
        for file in registeredFiles.values():
            currentFile = open(file['localPath'], 'w')
            currentFile.write(file['contents'])
            currentFile.close()

    def registerFile(self, remotePath, localPath, timestamp=""):
        with open(self.masterFile, 'a') as masterFile:
            masterFile.write(f"\n{remotePath} -> {localPath} - {timestamp}")

    def writeRemoteFiles(self, registeredFiles):
        newTreeBlobs = []
        for fileName in registeredFiles:
            newFileSha = self._createNewBlob(registeredFiles[fileName]["contents"])
            newTreeBlobs.append(self._createNewTreeBlob(fileName, GitHubRepo.fileMode, newFileSha))

        previousCommitSha = self._getPreviousCommit()
        if previousCommitSha == None:
            self._createBranch()
            previousCommitSha = self._getPreviousCommit()
            # newTreeSha = self._createTree(newTreeBlobs)
        currentTreeSha = self._getBranchTree(previousCommitSha)
        newTreeSha = self._updateTree(currentTreeSha, newTreeBlobs)
        
        newCommitSha = self._commitTree(newTreeSha, previousCommitSha)
        self._updateBranchReference(newCommitSha)

    def _checkRateLimits(self):
        return self._queryAPI("https://api.github.com/rate_limit")

def configureAccessTokens():
    while True:
        accessToken = input("Please input your GitHub access token (this will be stored in a .env file in this directory):\n>>> ")
        if accessToken == "exit" or accessToken == "back":
            break
        else:
            writeEnvFile(".env", accessToken)
            print("Successfully updated your access token!")
            break

def writeEnvFile(envFilePath, token):
    with open(envFilePath, "w") as file:
        file.write(f"TOKEN={token}")

def readEnvFile(envFilePath):
    with open(envFilePath, 'r') as file:
        token = file.readline().split("=")[-1]
    return token

def connectToGitHubRepo():
    username = input("Input your GitHub username:\n>>> ")
    if username == "back" or username == "exit":
        return
    repoName = input("Input the name of your repository:\n>>> ")
    if repoName == "back" or repoName == "exit":
        return
    hasToken = input("Have you already configured an access token? (y/n)\n>>> ")
    if hasToken == "back" or hasToken == "exit":
        return
    elif hasToken == "n" or hasToken == "no":
        configureAccessTokens()

    try:
        accessToken = readEnvFile(".env")
    except FileNotFoundError:
        print("Couldn't find .env file! Please reconfigure your access credentials.")
        return

    repo = GitHubRepo(username, repoName, accessToken)
    print("Connecting to your github repository!")
    
    res = requests.get(f"https://api.github.com/repos/{username}/{repoName}")

    if res.status_code == 200:
        print("Connection success!")

    elif res.json()["message"] == "Not Found":
        print("This repository doesn't exist!")
        return

    while True:
        print("""Please select an option:
1. Download files 
2. Upload files
3. Register a file
4. Deregister a file
5. View registered files
6. Back
7. Exit""")

        command = input(">>> ")

        if command == "1":
            remoteFiles = repo.readRemoteFiles()
            repo.writeLocalFiles(remoteFiles)
            print("Files successfully downloaded!")

        elif command == "2":
            localFiles = repo.readLocalFiles()
            repo.writeRemoteFiles(localFiles)
            print("Files successfully uploaded!")
            
        elif command == "3":
            registerNewFile(repo)

        elif command == "4":
            deregisterFile(repo)

        elif command == "5":
            displayRegisteredFiles(repo)
        
        elif command == "back" or command == "6":
            break

        elif command == "exit" or command == "7":
            exit()

        else:
            print("That's and invalid command.")
            
def registerNewFile(repository):
    while True:
        remoteName = input("What is the file name?\n>>> ")
        if remoteName == "back" or remoteName == "exit":
            break
        localPath = input("What is the full path to the file locally?\n>>> ")
        if localPath == "back" or localPath == "exit":
            break
        else:
            repository.registerFile(remoteName, localPath)
            print("File successfully registered!")
            break

def deregisterFile(repository):
    while True:
        fileName = input("What is the remote name of this file?\n>>> ")
        
        if fileName == "exit" or fileName == "back":
            break

        with open(repository.masterFile, 'r+') as masterFile:
            lines = masterFile.readlines()

            for i in range(len(lines)):
                if lines[i].split()[0] == fileName:
                    lines.pop(i)
                    break

            masterFile.seek(0)
            masterFile.writelines(lines)
            masterFile.truncate()
            print("Successfully deregistered file!")
            break

def displayRegisteredFiles(repository):
    with open(repository.masterFile, "r") as masterFile:
        print("Remote Name\tLocal Path")
        for line in masterFile.readlines()[1:]:
            print(line.strip())

def createNewRepo():
    username = input("Input your GitHub username:\n>>> ")
    if username == "back" or username == "exit":
        return
    repoName = input("Input the name of your new repository:\n>>> ")
    if repoName == "back" or repoName == "exit":
        return
    hasToken = input("Have you already configured an access token? (y/n)\n>>> ")
    if hasToken == "back" or hasToken == "exit":
        return
    elif hasToken == "n" or hasToken == "no":
        configureAccessTokens()

    GitHubRepo.createRemoteRepo(username, repoName, readEnvFile(".env"))

def main():
    while True:
        print("""Welcome to GitHubSync! Please select an option:
1) Connect to a GitHub Repository
2) Create new GitHub repository
3) Configure access tokens""")
        command = input(">>> ")
        
        if command == "1":
            connectToGitHubRepo()

        elif command == "2":
            createNewRepo()
            print("Repository created successfully!")

        elif command == "3":
            configureAccessTokens()

        elif command == "exit":
            print("Thanks for using GitHubSync!")
            exit()

        else:
            print("That's not a valid option.")

if __name__ == "__main__":
    if not os.path.exists(".master"):
        with open('.master', 'w') as file:
            file.write("[FILES]\n")

    while True:
        try:
            main()
        except Exception as e:
            print(f"An error occurred. Restarting!")