// Step 1: Get distinct second_resource_ids
val secondResourceIds = catalog_relationship.select(col("second_resource_id")).distinct()

// Step 2: Perform a LEFT JOIN and filter rows where `second_resource_id` is NULL (Top-level parents)
val getTopLevelParent = catalog_relationship
  .select(
    col("first_resource_id").alias("destination"),
    lit(null).cast("string").alias("source"),
    col("first_resource_id").alias("root")
  )
  .join(secondResourceIds, col("destination") === col("second_resource_id"), "left")
  .filter(col("second_resource_id").isNull)  // Retain only top-level parent nodes
  .drop("second_resource_id")

// Step 3: Recursive-like logic to establish full hierarchy
var secondResourceDF = catalog_relationship.as("al")
  .join(getTopLevelParent.as("gtlp"), col("gtlp.destination") === col("al.first_resource_id"))
  .select(
    col("al.second_resource_id").alias("destination"),
    col("al.first_resource_id").alias("source"),
    col("gtlp.root")
  )

// Recursive iteration to find more hierarchical connections
var iterationCount = 0
var finalDF = getTopLevelParent  // Initialize with top-level parents
while (secondResourceDF.count() > 0 && iterationCount < 100) {
  println(s"Iteration: $iterationCount, secondResourceDF Count: ${secondResourceDF.count()}")

  // Add new relationships to the final result
  finalDF = finalDF.union(secondResourceDF)

  // Continue building the hierarchy by joining recursively
  secondResourceDF = catalog_relationship.as("al")
    .join(secondResourceDF.as("gtlp"), col("gtlp.destination") === col("al.first_resource_id"))
    .select(
      col("al.second_resource_id").alias("destination"),
      col("al.first_resource_id").alias("source"),
      col("gtlp.root")
    )

  iterationCount += 1
}

// Step 4: Remove duplicates if necessary and show results
val TopLevelEs = finalDF.distinct()
