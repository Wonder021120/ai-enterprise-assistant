def read_job_description(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        return file.read()


def main() -> None:
    job_description = read_job_description("data/sample_job.txt")

    print("岗位 JD 内容：")
    print(job_description)


if __name__ == "__main__":
    main()